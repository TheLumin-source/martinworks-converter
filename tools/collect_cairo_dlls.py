# MartinWorks Converter
# Copyright (C) 2026 Martin de Lange
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero
# General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""
Collect the cairo DLL closure for a Windows build of the MartinWorks Converter.

cairosvg reaches cairo through cairocffi, which dlopens libcairo-2.dll at
runtime. PyInstaller cannot see that, so the DLL and everything it depends on
have to be copied in by hand.

The dependency list is read out of the PE import tables rather than written
down, because a hardcoded list silently rots whenever the source of the DLLs
changes (MSYS2 and the GTK runtime do not ship the same closure).

Run this on the Windows build machine, pointing it at the directory holding
the DLLs:

    python tools/collect_cairo_dlls.py --source C:/msys64/mingw64/bin --out cairo

Then build with converter.spec, which picks up whatever landed in ./cairo.
"""

import argparse
import os
import shutil
import struct
import sys

# Shipping these would override the OS copies and is how a build starts
# crashing on someone else's machine. They are always present on Windows.
SYSTEM_PREFIXES = ("api-ms-win-", "ext-ms-win-")
SYSTEM_DLLS = {
    "kernel32.dll", "user32.dll", "gdi32.dll", "advapi32.dll", "shell32.dll",
    "ole32.dll", "oleaut32.dll", "msvcrt.dll", "ucrtbase.dll", "ntdll.dll",
    "ws2_32.dll", "comdlg32.dll", "comctl32.dll", "rpcrt4.dll", "shlwapi.dll",
    "crypt32.dll", "dwmapi.dll", "imm32.dll", "winmm.dll", "version.dll",
    "setupapi.dll", "bcrypt.dll", "userenv.dll", "dnsapi.dll", "iphlpapi.dll",
    "secur32.dll", "wldap32.dll", "gdiplus.dll", "d3d11.dll", "dxgi.dll",
    "opengl32.dll", "glu32.dll", "mscoree.dll", "powrprof.dll", "psapi.dll",
    "netapi32.dll", "ws2help.dll", "winspool.drv", "uxtheme.dll", "usp10.dll",
    "msimg32.dll", "winhttp.dll", "wintrust.dll", "cfgmgr32.dll", "urlmon.dll",
    "wininet.dll", "authz.dll", "avicap32.dll", "msacm32.dll", "dbghelp.dll",
    "normaliz.dll", "cryptbase.dll", "profapi.dll", "kernelbase.dll",
    "vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll", "concrt140.dll",
}


def _rva_to_offset(rva, sections):
    for va, vsize, raw_ptr, raw_size in sections:
        if va <= rva < va + max(vsize, raw_size):
            return raw_ptr + (rva - va)
    return None


def _cstring(data, offset):
    end = data.find(b"\x00", offset)
    return data[offset:end].decode("ascii", "replace") if end != -1 else ""


def pe_imports(path):
    """Return the DLL names a PE file imports, including delay-loaded ones."""
    with open(path, "rb") as f:
        data = f.read()
    if len(data) < 0x40 or data[:2] != b"MZ":
        return []
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if pe + 24 > len(data) or data[pe:pe + 4] != b"PE\x00\x00":
        return []

    n_sections = struct.unpack_from("<H", data, pe + 6)[0]
    opt_size = struct.unpack_from("<H", data, pe + 20)[0]
    magic = struct.unpack_from("<H", data, pe + 24)[0]
    # PE32 keeps 96 bytes before the data directories, PE32+ keeps 112.
    dd_offset = pe + 24 + (96 if magic == 0x10B else 112)

    sec_offset = pe + 24 + opt_size
    sections = []
    for i in range(n_sections):
        base = sec_offset + i * 40
        if base + 40 > len(data):
            break
        vsize, va, raw_size, raw_ptr = struct.unpack_from("<IIII", data, base + 8)
        sections.append((va, vsize, raw_ptr, raw_size))

    names = []
    # Directory 1 is the import table, 13 the delay-load import table.
    for index, name_field in ((1, 12), (13, 4)):
        entry = dd_offset + index * 8
        if entry + 8 > len(data):
            continue
        dir_rva = struct.unpack_from("<I", data, entry)[0]
        if not dir_rva:
            continue
        offset = _rva_to_offset(dir_rva, sections)
        if offset is None:
            continue
        size = 20 if index == 1 else 32
        while offset + size <= len(data):
            chunk = data[offset:offset + size]
            if not any(chunk):
                break
            name_rva = struct.unpack_from("<I", data, offset + name_field)[0]
            if name_rva:
                name_off = _rva_to_offset(name_rva, sections)
                if name_off is not None and name_off < len(data):
                    got = _cstring(data, name_off)
                    if got:
                        names.append(got)
            offset += size
    return names


def is_system(name):
    low = name.lower()
    return low in SYSTEM_DLLS or any(low.startswith(p) for p in SYSTEM_PREFIXES)


def resolve(name, roots):
    for root in roots:
        candidate = os.path.join(root, name)
        if os.path.isfile(candidate):
            return candidate
        # Windows filesystems are case insensitive; Linux build hosts are not.
        try:
            for entry in os.listdir(root):
                if entry.lower() == name.lower():
                    return os.path.join(root, entry)
        except OSError:
            pass
    return None


def closure(seeds, roots):
    """Walk imports breadth first. Returns (resolved paths, unresolved names)."""
    seen, found, missing = set(), {}, set()
    queue = list(seeds)
    while queue:
        current = queue.pop(0)
        key = os.path.basename(current).lower()
        if key in seen:
            continue
        seen.add(key)
        path = current if os.path.isfile(current) else resolve(current, roots)
        if not path:
            if not is_system(current):
                missing.add(current)
            continue
        found[key] = path
        for dep in pe_imports(path):
            if is_system(dep) or dep.lower() in seen:
                continue
            queue.append(dep)
    return found, missing


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", action="append", required=True,
                    help="Directory holding the DLLs. Repeatable.")
    ap.add_argument("--out", default="cairo", help="Output directory.")
    ap.add_argument("--seed", action="append",
                    default=None, help="Seed DLL names. Defaults to cairo's.")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    roots = [os.path.abspath(s) for s in args.source]
    for r in roots:
        if not os.path.isdir(r):
            sys.exit(f"Source directory does not exist: {r}")

    seeds = args.seed or ["libcairo-2.dll"]
    resolved_seeds = []
    for s in seeds:
        hit = resolve(s, roots)
        if not hit:
            sys.exit(f"Could not find {s} in: {', '.join(roots)}")
        resolved_seeds.append(hit)

    found, missing = closure(resolved_seeds, roots)
    total = sum(os.path.getsize(p) for p in found.values())
    print(f"{len(found)} DLLs, {total / 1024 / 1024:.1f} MB")
    for name in sorted(found):
        print(f"  {name}")
    if missing:
        print("\nUnresolved (check the source directory is complete):")
        for name in sorted(missing):
            print(f"  {name}")

    if args.dry_run:
        return 1 if missing else 0
    os.makedirs(args.out, exist_ok=True)
    for name, path in sorted(found.items()):
        shutil.copy2(path, os.path.join(args.out, os.path.basename(path)))
    print(f"\nCopied into {os.path.abspath(args.out)}")
    # An incomplete closure produces a build that fails only at runtime, on
    # someone else's machine, so make it a build failure here instead.
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())

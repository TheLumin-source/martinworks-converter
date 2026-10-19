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
Image conversion engine for the MartinWorks Converter.

Deliberately free of tkinter so the conversion logic can run headless: the
--selftest path, CI on a runner with no display, and any future command line
use all import this module without needing a GUI toolkit installed.

Raster formats go through Pillow. SVG is an input-only format and is rendered
to pixels first, because a raster image cannot be turned back into vectors.
"""

import gzip
import io
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageOps

# Single source of truth for the version. The VERSION file at the repo root is
# also what installer.iss reads, so the app and the installer cannot drift.
def _read_version():
    for d in (_bundle_root_early(), os.path.dirname(os.path.abspath(__file__))):
        try:
            with open(os.path.join(d, "VERSION"), encoding="utf-8") as fh:
                v = fh.read().strip()
            if v:
                return v
        except OSError:
            continue
    return "0.0.0"


def _bundle_root_early():
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


__version__ = _read_version()


# --- Windows cairo lookup ----------------------------------------------------

# Where a frozen build keeps its DLLs, relative to the bundle root. PyInstaller
# unpacks to sys._MEIPASS (onefile) or _internal (onedir); both answer to the
# same attribute, so one path covers the pair.
CAIRO_BUNDLE_DIR = "cairo"


def _bundle_root():
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def _prepare_windows_cairo():
    """Put the bundled cairo DLLs on the search path before cairocffi looks.

    cairocffi resolves the library with ctypes.util.find_library('libcairo-2'),
    which on Windows scans PATH, and falls back to dlopen('libcairo-2.dll').
    Neither consults the bundle, so a frozen build finds nothing unless the
    directory is registered first. Returns the directory used, or None.
    """
    if not sys.platform.startswith("win"):
        return None
    root = _bundle_root()
    candidates = [
        os.path.join(root, CAIRO_BUNDLE_DIR),
        root,
        # onedir builds run from the exe folder with DLLs one level down.
        os.path.join(os.path.dirname(sys.executable), "_internal", CAIRO_BUNDLE_DIR),
        os.path.join(os.path.dirname(sys.executable), CAIRO_BUNDLE_DIR),
    ]
    found = None
    for d in candidates:
        if not os.path.isdir(d):
            continue
        if not any(f.lower().startswith("libcairo") and f.lower().endswith(".dll")
                   for f in os.listdir(d)):
            continue
        # add_dll_directory covers dlopen; PATH is what find_library reads, and
        # a full path back from find_library is the most reliable outcome.
        try:
            os.add_dll_directory(d)
        except (AttributeError, OSError):
            pass
        os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
        found = found or d
    return found


CAIRO_DLL_DIR = _prepare_windows_cairo()


# --- Formats -----------------------------------------------------------------

# key: (extension, Pillow format name, keeps an alpha channel)
FORMATS = {
    "PNG":  (".png",  "PNG",  True),
    "JPEG": (".jpg",  "JPEG", False),
    "WebP": (".webp", "WEBP", True),
    "BMP":  (".bmp",  "BMP",  False),
    "GIF":  (".gif",  "GIF",  True),
    "TIFF": (".tiff", "TIFF", True),
    "ICO":  (".ico",  "ICO",  True),
}
QUALITY_FORMATS = {"JPEG", "WebP"}

# Vector input. Not in FORMATS: these are things we can read, never write.
SVG_EXTENSIONS = {".svg", ".svgz"}

IMAGE_EXTENSIONS = [
    ".png", ".jpg", ".jpeg", ".jpe", ".jfif", ".webp", ".bmp", ".dib",
    ".gif", ".tif", ".tiff", ".ico", ".ppm", ".pgm", ".tga", ".heic",
    ".svg", ".svgz",
]


def unique_path(path):
    """Return `path`, or path with ' (1)', ' (2)'... if it already exists."""
    if not os.path.exists(path):
        return path
    root, ext = os.path.splitext(path)
    i = 1
    while True:
        candidate = f"{root} ({i}){ext}"
        if not os.path.exists(candidate):
            return candidate
        i += 1


def human_size(num_bytes):
    """Format a byte count as a short human-readable string (e.g. '1.2 MB')."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024


# --- SVG rasterising ---------------------------------------------------------

def _svg_backend():
    """Pick an available SVG renderer.

    cairosvg is preferred because it is in-process and needs no temp files.
    rsvg-convert and Inkscape are the fallbacks: both are common on Linux and
    let the feature work on a machine where the Python binding is missing or
    its cairo library failed to load.
    """
    # An explicit choice wins, so each backend can be exercised on a machine
    # that happens to have several installed.
    forced = os.environ.get("CONVERTER_SVG_BACKEND", "").strip().lower()
    if forced:
        if forced in ("cairosvg", "resvg"):
            module = "cairosvg" if forced == "cairosvg" else "resvg_py"
            try:
                __import__(module)
                return forced, None
            except Exception as e:  # noqa: BLE001
                return None, f"CONVERTER_SVG_BACKEND={forced} but it failed to import: {e}"
        if shutil.which(forced):
            return forced, None
        return None, f"CONVERTER_SVG_BACKEND={forced} but that renderer was not found"

    try:
        import cairosvg  # noqa: F401
        return "cairosvg", None
    except Exception as e:  # noqa: BLE001
        cairo_error = str(e)
    # resvg_py is a single self-contained extension with no system dependency,
    # which is what makes it the dependable one in a frozen Windows build.
    try:
        import resvg_py  # noqa: F401
        return "resvg", None
    except Exception:  # noqa: BLE001
        pass
    for exe, name in (("rsvg-convert", "rsvg-convert"), ("inkscape", "inkscape")):
        if shutil.which(exe):
            return name, None
    return None, (
        "No SVG renderer available. Install cairosvg (needs a system cairo) "
        "or resvg-py (self-contained), or rsvg-convert, or Inkscape. "
        f"cairosvg import failed with: {cairo_error}"
    )


SVG_BACKEND, SVG_ERROR = _svg_backend()
SVG_AVAILABLE = SVG_BACKEND is not None


def is_svg(path):
    return os.path.splitext(path)[1].lower() in SVG_EXTENSIONS


def _read_svg_bytes(path):
    """Return raw SVG markup, transparently decompressing .svgz."""
    with open(path, "rb") as f:
        data = f.read()
    # .svgz is gzipped SVG. Sniff the magic number rather than trusting the
    # extension, since plenty of .svg files in the wild are gzipped too.
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return data


def rasterize_svg(src_path, width=0):
    """Render an SVG to an RGBA PIL Image.

    `width` in pixels, or 0 to use the size declared in the file. Height is
    always derived from the aspect ratio, so output is never distorted.
    """
    if not SVG_AVAILABLE:
        raise RuntimeError(SVG_ERROR)
    width = int(width) if width else 0

    if SVG_BACKEND == "cairosvg":
        import cairosvg
        kwargs = {"bytestring": _read_svg_bytes(src_path)}
        if width > 0:
            kwargs["output_width"] = width
        # cairosvg defaults to unsafe=False, which blocks external entity and
        # file references. An SVG is untrusted XML, so leave that default be.
        png = cairosvg.svg2png(**kwargs)
        return Image.open(io.BytesIO(png)).convert("RGBA")

    if SVG_BACKEND == "resvg":
        import resvg_py
        kwargs = {"svg_string": _read_svg_bytes(src_path).decode("utf-8", "replace")}
        if width > 0:
            kwargs["width"] = width
        png = bytes(resvg_py.svg_to_bytes(**kwargs))
        return Image.open(io.BytesIO(png)).convert("RGBA")

    # External renderers write a file, so stage it in a temp dir.
    tmpdir = tempfile.mkdtemp(prefix="conv_svg_")
    try:
        out = os.path.join(tmpdir, "out.png")
        if SVG_BACKEND == "rsvg-convert":
            cmd = ["rsvg-convert", "-f", "png", "-o", out]
            if width > 0:
                cmd += ["-w", str(width)]
            cmd.append(src_path)
        else:
            cmd = ["inkscape", "--export-type=png", f"--export-filename={out}"]
            if width > 0:
                cmd.append(f"--export-width={width}")
            cmd.append(src_path)
        proc = subprocess.run(cmd, capture_output=True, timeout=120, check=False)
        if proc.returncode != 0 or not os.path.exists(out):
            detail = (proc.stderr or b"").decode("utf-8", "replace").strip()
            raise RuntimeError(f"{SVG_BACKEND} failed: {detail or 'no output produced'}")
        with Image.open(out) as im:
            return im.convert("RGBA")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# --- Conversion --------------------------------------------------------------

def convert_image(src_path, target_key, quality, output_dir,
                  background=(255, 255, 255), svg_width=0):
    """Convert a single image. Returns (dest_path, size_in_bytes) of the file written.

    `svg_width` only applies when the source is an SVG; raster sources ignore it.
    """
    ext, pil_format, supports_alpha = FORMATS[target_key]

    if is_svg(src_path):
        source = rasterize_svg(src_path, svg_width)
    else:
        source = Image.open(src_path)

    with source as im:
        im = ImageOps.exif_transpose(im)  # respect EXIF orientation

        if supports_alpha:
            if pil_format == "GIF":
                if im.mode not in ("RGBA", "LA", "P"):
                    im = im.convert("RGBA")
            else:
                if im.mode not in ("RGBA", "RGB", "LA", "L"):
                    im = im.convert("RGBA")
        else:
            if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                rgba = im.convert("RGBA")
                flat = Image.new("RGB", rgba.size, background)
                flat.paste(rgba, mask=rgba.split()[-1])
                im = flat
            elif im.mode != "RGB":
                im = im.convert("RGB")

        base = os.path.splitext(os.path.basename(src_path))[0]
        dest = unique_path(os.path.join(output_dir, base + ext))

        save_kwargs = {}
        if pil_format in ("JPEG", "WEBP"):
            save_kwargs["quality"] = int(quality)
        if pil_format == "JPEG":
            save_kwargs["optimize"] = True
        if pil_format == "ICO":
            w, h = im.size
            sizes = [s for s in (16, 24, 32, 48, 64, 128, 256) if s <= max(w, h)]
            save_kwargs["sizes"] = [(s, s) for s in sizes] or [(w, h)]

        im.save(dest, pil_format, **save_kwargs)
        return dest, os.path.getsize(dest)

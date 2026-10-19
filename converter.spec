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

# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the MartinWorks Converter.

Build:
    python tools/collect_cairo_dlls.py --source C:/msys64/mingw64/bin --out cairo
    pyinstaller converter.spec

The cairo step is separate on purpose: cairosvg loads libcairo-2.dll through
cffi at runtime, so PyInstaller's import analysis never sees it and cannot
collect it. Skipping that step still produces a working build, it just falls
back to the resvg renderer for SVG.
"""

import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

APP_NAME = "Image Converter"
HERE = os.path.abspath(os.getcwd())

# The collector drops the whole closure here. Bundled under a "cairo" folder so
# image_engine._prepare_windows_cairo knows where to look.
cairo_binaries = []
cairo_dir = os.path.join(HERE, "cairo")
if os.path.isdir(cairo_dir):
    for name in sorted(os.listdir(cairo_dir)):
        if name.lower().endswith(".dll"):
            cairo_binaries.append((os.path.join(cairo_dir, name), "cairo"))

datas = [("fonts", "fonts"), ("icon.ico", "."), ("icon.png", "."), ("VERSION", ".")]
datas += collect_data_files("cairosvg", include_py_files=False)

hiddenimports = [
    # Reached through cffi at runtime, so the analysis cannot infer them.
    "cairocffi", "cairosvg", "cffi", "_cffi_backend",
    # The renderer that needs no system libraries. Keeping it in means a build
    # without the cairo DLLs still converts SVG.
    "resvg_py",
]
hiddenimports += collect_submodules("cairosvg")

a = Analysis(
    ["image_converter.py"],
    pathex=[HERE],
    binaries=cairo_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    strip=False,
    upx=False,          # UPX corrupts some cairo DLLs, so leave them alone.
    console=False,      # GUI app: no console window.
    icon="icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=APP_NAME,
)

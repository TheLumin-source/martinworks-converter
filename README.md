# MartinWorks Converter

A drag-and-drop desktop converter for images and documents. Everything runs on
your own machine: nothing is uploaded anywhere.

- **Images:** PNG, JPG, WebP, BMP, GIF, TIFF, ICO, and SVG in
- **Documents:** PDF, DOCX, TXT, HTML, Markdown, RTF

Drop files or whole folders onto a tab, pick an output format, convert. Each row
reports its own result and output size.

## Install from source

Python 3.10 or newer. Tkinter is **not** on PyPI, so install it from your
package manager first:

```bash
sudo apt install python3-tk        # Debian / Ubuntu / Mint
sudo pacman -S tk                 # Arch
sudo dnf install python3-tkinter  # Fedora
```

On Windows the python.org installer already includes it.

Then:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Run

```bash
./image-converter.sh
```

On Windows, use `Image Converter.bat`, or run `python image_converter.py`.

To add a menu entry and a desktop shortcut on Linux:

```bash
./image-converter.sh --install-desktop
```

## Check it works

The conversion engine has no tkinter import, and `--selftest` exits before the
GUI loads, so both run headless with no display:

```bash
python image_converter.py --selftest
python -m pytest tests -q
```

`--selftest` performs real conversions and prints a PASS/FAIL line per job,
including the negative cases. That is also the fastest way to see which SVG
backend you ended up on.

## SVG notes

SVG is **input only**. There is no raster-to-SVG target, because turning a
bitmap back into vector paths is a tracing problem, not a conversion.

Two renderers are supported, tried in this order:

1. **CairoSVG**, preferred. Needs a system cairo, which Linux normally has.
2. **resvg-py**, fallback. One self-contained wheel, no system library at all.

Force one with `CONVERTER_SVG_BACKEND=cairosvg` or `=resvg`. If neither is
available the Images tab still works for raster formats and says why SVG is off.

Set an output width in the Images tab to scale an SVG on the way out. Height
follows the aspect ratio. Leave it at 0 for the SVG's native size.

## Building a Windows installer

```bash
python tools/collect_cairo_dlls.py --source C:/msys64/mingw64/bin --out cairo
pyinstaller converter.spec
```

The first step exists because CairoSVG does not link cairo: cairocffi opens
`libcairo-2.dll` at runtime, which PyInstaller's import analysis cannot see. The
script walks the PE import tables to collect the actual dependency closure
rather than a hardcoded list, since MSYS2 and the GTK runtime ship different
ones. `image_engine._prepare_windows_cairo` then registers that folder before
cairocffi looks for the library.

Skipping the cairo step is survivable: the build falls back to resvg-py. The
frozen app's `--selftest` log prints `bundled cairo dir:`, and `NONE` there
means the DLLs did not make it in.

Then `installer.iss` packages the one-folder build with Inno Setup. All its
paths are relative to the repo, and the version comes from the `VERSION` file.

## Status

Tested on Linux, where the engine and both SVG backends pass the suite above.

The Windows build path is verified by unit test rather than by a build: the PE
walker and the cairo discovery logic are both covered, but no Windows machine
has produced an installer from this tree yet. Treat the first Windows build as
unproven and check that `--selftest` line.

## Licence

Free and open source under the **GNU Affero General Public License, version 3
or later**. The full text is in [LICENSE](LICENSE).

In short: use it, study it, change it, share it. If you distribute a modified
version, or run one as a network service, your users get the same source rights
you got. Nobody gets to close it back up.

This also keeps the project honest about what it is built on. PyMuPDF is AGPL-3.0
and the bundled Pandoc is GPL-2.0-or-later, so a distributed build was always
going to carry copyleft terms. Licensing the whole thing under the AGPL matches
that instead of papering over it. See
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) for every dependency licence.

Copyright (C) 2026 Martin de Lange, trading as MartinWorks.

The licence covers the code. `icon.ico` and `icon.png` are the MartinWorks mark:
please use your own icon rather than shipping something that looks like it came
from MartinWorks when it did not. Bundled fonts are under the SIL Open Font
License 1.1, see [fonts/OFL.txt](fonts/OFL.txt).

## Contributing

Issues and pull requests are welcome. Please run both checks before opening one:

```bash
python image_converter.py --selftest
python -m pytest tests -q
```

Contributions are taken under the AGPL-3.0-or-later, same as the rest.

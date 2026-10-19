# Third party notices

MartinWorks Converter does the conversions through other people's libraries.
None of them are vendored into this repository: pip fetches them from the
versions pinned in `requirements.txt`. They keep their own licences, listed
here so anyone building or redistributing the app knows what applies.

## Runtime dependencies

| Package | Licence | Used for |
| --- | --- | --- |
| Pillow | MIT-CMU (HPND) | all raster image reading and writing |
| CairoSVG | LGPL-3.0-or-later | preferred SVG renderer |
| cairocffi | BSD-3-Clause | how CairoSVG reaches the cairo library |
| resvg-py | MIT (wraps resvg, MPL-2.0) | fallback SVG renderer, no system cairo needed |
| tkinterdnd2 | MIT | optional drag and drop |
| pypandoc-binary | MIT (wrapper) | runs Pandoc for document conversion |
| Pandoc | **GPL-2.0-or-later** | the document conversion engine itself, bundled inside pypandoc-binary |
| PyMuPDF | **AGPL-3.0**, or a commercial licence from Artifex | reading PDFs |
| pdf2docx | MIT | high fidelity PDF to Word |
| xhtml2pdf | Apache-2.0 | writing PDFs |
| striprtf | BSD-3-Clause | reading RTF |

Tkinter is part of the Python standard library and is not installed from PyPI.

## Bundled assets

The fonts in `fonts/` are the only third party files actually committed here.
Cinzel and Crimson Pro are both under the SIL Open Font License 1.1, which
allows bundling and redistribution with software. See `fonts/OFL.txt` and
`fonts/README.md`.

`icon.ico` and `icon.png` are the MartinWorks mark. The code licence covers the
code, not the brand: please do not ship the icons on something that looks like
it came from MartinWorks when it did not. Swap in your own icon instead.

## If you redistribute a build

Running this from source is straightforward: pip installs the dependencies on
your own machine and each licence applies to you directly.

Shipping a built bundle (a PyInstaller folder, or an installer made with
`installer.iss`) is different, because the bundle then contains those libraries
as well as this code. Two of them carry copyleft terms worth reading before you
do that:

- **Pandoc** is GPL-2.0-or-later, and pypandoc-binary bundles the Pandoc
  executable. The app runs it as a separate process, which keeps it at arm's
  length, but a bundle that ships the binary has to carry its licence and offer
  its source.
- **PyMuPDF** is AGPL-3.0, and `doc_converter.py` imports it in process. A
  distributed bundle that includes it is a combined work under the AGPL, so the
  complete corresponding source has to be available. That is one reason this
  repository exists and is public. Artifex sells a commercial licence if you
  need to ship it under different terms.

Nothing here is legal advice. If you plan to sell or redistribute a build,
read those two licences yourself.

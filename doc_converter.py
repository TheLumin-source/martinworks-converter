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
Document conversion engine for the Image/File Converter app.
=============================================================
Converts between PDF, DOCX, TXT, HTML, Markdown and RTF.

Strategy (one engine per job, picked for fidelity):
- Pandoc (bundled via pypandoc_binary) for DOCX / HTML / MD / TXT <-> each other
- PyMuPDF for reading PDFs (PDF -> text / html)
- pdf2docx for high-fidelity PDF -> Word
- xhtml2pdf for writing PDFs (anything -> html -> pdf)
- striprtf for reading RTF (Pandoc can write RTF but not read it)

Public API:
    DOC_FORMATS                      # {".pdf": "PDF", ...} input extensions -> label
    TARGET_FORMATS                   # ordered list of (label, ext) for the UI
    convert_document(src, ext, out)  # -> (dest_path, size_bytes)
"""

import os
import shutil

import pypandoc

try:
    import pymupdf as fitz
except ImportError:  # older wheels expose the legacy name
    import fitz


# Input extensions we accept, mapped to a friendly label.
DOC_FORMATS = {
    ".pdf":  "PDF",
    ".docx": "DOCX",
    ".txt":  "TXT",
    ".html": "HTML",
    ".htm":  "HTML",
    ".md":   "Markdown",
    ".markdown": "Markdown",
    ".rtf":  "RTF",
}

# What the user can convert *to* (label shown in the dropdown -> extension written).
TARGET_FORMATS = [
    ("PDF", ".pdf"),
    ("DOCX", ".docx"),
    ("TXT", ".txt"),
    ("HTML", ".html"),
    ("Markdown", ".md"),
    ("RTF", ".rtf"),
]

# Pandoc reader/writer names keyed by file extension.
PANDOC_READ = {
    ".txt": "markdown", ".md": "markdown", ".markdown": "markdown",
    ".html": "html", ".htm": "html", ".docx": "docx",
}
PANDOC_WRITE = {
    ".txt": "plain", ".md": "gfm", ".html": "html", ".docx": "docx", ".rtf": "rtf",
}
# Writers that need a full standalone document rather than a fragment.
_STANDALONE = {".html", ".rtf"}


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


def _writer_args(target_ext):
    return ["--standalone"] if target_ext in _STANDALONE else []


# Minimal, xhtml2pdf-friendly wrapper. Pandoc's own --standalone template uses
# modern CSS (e.g. :not(:hover)) that xhtml2pdf's CSS parser rejects, so for the
# PDF path we take a bare Pandoc fragment and wrap it in this simple stylesheet.
_HTML_WRAPPER = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
@page {{ size: A4; margin: 2cm; }}
body {{ font-family: Helvetica, Arial, sans-serif; font-size: 11pt; line-height: 1.4; color: #000; }}
h1 {{ font-size: 20pt; }} h2 {{ font-size: 16pt; }} h3 {{ font-size: 13pt; }}
pre, code {{ font-family: Courier, monospace; font-size: 10pt; background: #f4f4f4; }}
table {{ border-collapse: collapse; }} td, th {{ border: 1px solid #888; padding: 4px; }}
img {{ max-width: 100%; }} blockquote {{ color: #555; margin-left: 1em; }}
</style></head><body>
{body}
</body></html>"""


def _wrap_html(fragment):
    return _HTML_WRAPPER.format(body=fragment)


# --- PDF readers -------------------------------------------------------------

def _pdf_to_text(src):
    with fitz.open(src) as doc:
        return "\n\n".join(page.get_text("text") for page in doc)


def _pdf_to_html(src):
    with fitz.open(src) as doc:
        body = "\n".join(page.get_text("html") for page in doc)
    return f"<!DOCTYPE html><html><head><meta charset='utf-8'></head><body>{body}</body></html>"


def _from_pdf(src, target_ext, dest):
    if target_ext == ".docx":
        from pdf2docx import Converter
        cv = Converter(src)
        try:
            cv.convert(dest)
        finally:
            cv.close()
    elif target_ext == ".html":
        with open(dest, "w", encoding="utf-8") as f:
            f.write(_pdf_to_html(src))
    elif target_ext in (".txt", ".md"):
        with open(dest, "w", encoding="utf-8") as f:
            f.write(_pdf_to_text(src))
    elif target_ext == ".rtf":
        pypandoc.convert_text(_pdf_to_text(src), "rtf", format="markdown",
                              outputfile=dest, extra_args=["--standalone"])
    else:
        raise ValueError(f"Unsupported PDF target: {target_ext}")


# --- writing PDFs ------------------------------------------------------------

def _to_html(src, src_ext):
    if src_ext in (".html", ".htm"):
        with open(src, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    fragment = pypandoc.convert_file(src, "html", format=PANDOC_READ[src_ext])
    return _wrap_html(fragment)


def _html_to_pdf(html, dest):
    from xhtml2pdf import pisa
    with open(dest, "wb") as f:
        result = pisa.CreatePDF(html, dest=f, encoding="utf-8")
    if result.err:
        raise RuntimeError(f"PDF rendering reported {result.err} error(s)")


# --- text-source helpers (RTF in, or plain text) -----------------------------

def _rtf_to_text(src):
    from striprtf.striprtf import rtf_to_text
    with open(src, "r", encoding="utf-8", errors="replace") as f:
        return rtf_to_text(f.read())


def _from_text(text, target_ext, dest):
    if target_ext == ".pdf":
        fragment = pypandoc.convert_text(text, "html", format="markdown")
        _html_to_pdf(_wrap_html(fragment), dest)
    else:
        pypandoc.convert_text(text, PANDOC_WRITE[target_ext], format="markdown",
                              outputfile=dest, extra_args=_writer_args(target_ext))


# --- public entry point ------------------------------------------------------

def convert_document(src_path, target_ext, output_dir):
    """Convert one document. Returns (dest_path, size_in_bytes)."""
    src_ext = os.path.splitext(src_path)[1].lower()
    if src_ext not in DOC_FORMATS:
        raise ValueError(f"Unsupported input type: {src_ext}")

    base = os.path.splitext(os.path.basename(src_path))[0]
    dest = unique_path(os.path.join(output_dir, base + target_ext))

    # Same logical format (incl. .htm/.html, .md/.markdown) -> just copy.
    if DOC_FORMATS[src_ext] == _label_for(target_ext):
        shutil.copyfile(src_path, dest)
        return dest, os.path.getsize(dest)

    if src_ext == ".pdf":
        _from_pdf(src_path, target_ext, dest)
    elif src_ext == ".rtf":
        _from_text(_rtf_to_text(src_path), target_ext, dest)
    elif target_ext == ".pdf":
        _html_to_pdf(_to_html(src_path, src_ext), dest)
    else:
        pypandoc.convert_file(src_path, PANDOC_WRITE[target_ext],
                              format=PANDOC_READ[src_ext], outputfile=dest,
                              extra_args=_writer_args(target_ext))

    return dest, os.path.getsize(dest)


def _label_for(ext):
    for label, e in TARGET_FORMATS:
        if e == ext:
            return label
    return None

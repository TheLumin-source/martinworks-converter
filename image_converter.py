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
MartinWorks Converter
=====================
A drag-and-drop desktop app with two tabs:

- Images:    convert between PNG / JPG / WebP / BMP / GIF / TIFF / ICO
- Documents: convert between PDF / DOCX / TXT / HTML / Markdown / RTF

Drag files OR whole folders onto a tab, pick the output format, and convert.
Results (with output file sizes) appear per row.

Styled to match martinworks.org: antique gold on near-black, Cinzel headings +
Crimson Pro body (fonts bundled in ./fonts and loaded privately at runtime).

Built with Tkinter + Pillow (images) + Pandoc/PyMuPDF/xhtml2pdf (documents),
with tkinterdnd2 for drag & drop.
"""

import os
import sys
import glob
import threading
import traceback
from PIL import Image

from image_engine import (
    FORMATS, QUALITY_FORMATS, IMAGE_EXTENSIONS, SVG_AVAILABLE, SVG_BACKEND,
    SVG_ERROR, convert_image, human_size,
)

# Drag-and-drop is optional: the app still runs (Browse only) without it.
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    DND_AVAILABLE = True
except Exception:
    TkinterDnD = None
    DND_FILES = None
    DND_AVAILABLE = False

# Document engine is optional: if its libraries fail to import, the Images tab
# still works and the Documents tab shows why it's unavailable.
try:
    import doc_converter
    DOC_AVAILABLE = True
    DOC_IMPORT_ERROR = ""
except Exception as e:  # noqa: BLE001
    doc_converter = None
    DOC_AVAILABLE = False
    DOC_IMPORT_ERROR = str(e)


def _selftest():
    """Run real conversions and write a PASS/FAIL report to a log file."""
    import tempfile
    lines = []
    try:
        tmp = tempfile.mkdtemp(prefix="conv_selftest_")
        src = os.path.join(tmp, "t.png")
        Image.new("RGBA", (40, 30), (0, 150, 200, 255)).save(src)
        dest, size = convert_image(src, "JPEG", 85, tmp)
        lines.append(f"image PNG->JPEG: {os.path.basename(dest)} {size}B")

        # SVG is input-only and goes through a separate rasterising path, so
        # it gets its own checks rather than riding on the raster ones.
        lines.append(f"svg backend: {SVG_BACKEND or 'NONE'}")
        if sys.platform.startswith("win"):
            import image_engine
            lines.append(f"bundled cairo dir: {image_engine.CAIRO_DLL_DIR or 'NONE'}")
        if SVG_AVAILABLE:
            svg_src = os.path.join(tmp, "t.svg")
            with open(svg_src, "w", encoding="utf-8") as f:
                f.write('<svg xmlns="http://www.w3.org/2000/svg" width="64" height="32" '
                        'viewBox="0 0 64 32"><rect width="64" height="32" fill="#c8922a"/>'
                        '<circle cx="16" cy="16" r="10" fill="#141210"/></svg>')

            dest, size = convert_image(svg_src, "PNG", 90, tmp)
            with Image.open(dest) as im:
                got = im.size
            assert got == (64, 32), f"native size wrong: {got}"
            lines.append(f"svg SVG->PNG (native): {os.path.basename(dest)} {got} {size}B")

            # An explicit width must scale and must keep the aspect ratio.
            dest, size = convert_image(svg_src, "PNG", 90, tmp, svg_width=256)
            with Image.open(dest) as im:
                got = im.size
            assert got == (256, 128), f"scaled size wrong: {got}"
            lines.append(f"svg SVG->PNG (w=256): {os.path.basename(dest)} {got} {size}B")

            # Into a format with no alpha, to exercise the flattening path.
            dest, size = convert_image(svg_src, "JPEG", 85, tmp, svg_width=128)
            with Image.open(dest) as im:
                assert im.mode == "RGB", f"JPEG mode wrong: {im.mode}"
            lines.append(f"svg SVG->JPEG: {os.path.basename(dest)} {size}B")

            # Gzipped SVG, which is what .svgz and many exported .svg files are.
            import gzip
            svgz_src = os.path.join(tmp, "t.svgz")
            with open(svg_src, "rb") as f_in, gzip.open(svgz_src, "wb") as f_out:
                f_out.write(f_in.read())
            dest, size = convert_image(svgz_src, "PNG", 90, tmp)
            lines.append(f"svg SVGZ->PNG: {os.path.basename(dest)} {size}B")

            # Negative: malformed SVG must fail loudly, not write a broken file.
            bad = os.path.join(tmp, "bad.svg")
            with open(bad, "w", encoding="utf-8") as f:
                f.write("<svg><unclosed>")
            try:
                convert_image(bad, "PNG", 90, tmp)
                lines.append("NEGATIVE FAILED: malformed SVG was accepted")
            except Exception:
                lines.append("negative malformed SVG: rejected as expected")
        else:
            lines.append("SVG NOT AVAILABLE: " + (SVG_ERROR or ""))

        # Negative: a missing source must raise rather than half-write output.
        try:
            convert_image(os.path.join(tmp, "nope.png"), "PNG", 90, tmp)
            lines.append("NEGATIVE FAILED: missing file was accepted")
        except Exception:
            lines.append("negative missing file: rejected as expected")

        if DOC_AVAILABLE:
            import pypandoc
            lines.append("pandoc: " + pypandoc.get_pandoc_version())
            md = os.path.join(tmp, "t.md")
            with open(md, "w", encoding="utf-8") as f:
                f.write("# Title\n\nSome **body** text.\n")
            for ext in (".pdf", ".docx", ".html", ".txt"):
                dest, size = doc_converter.convert_document(md, ext, tmp)
                lines.append(f"doc MD->{ext}: {os.path.basename(dest)} {size}B")
        else:
            lines.append("DOC NOT AVAILABLE: " + DOC_IMPORT_ERROR)
        if any(l.startswith("NEGATIVE FAILED") for l in lines):
            lines.append("SELFTEST FAILED: a negative case was accepted")
        else:
            lines.append("SELFTEST PASSED")
    except Exception as e:  # noqa: BLE001
        lines.append("SELFTEST FAILED: " + repr(e))
        lines.append(traceback.format_exc())

    import tempfile as _tf
    args = sys.argv[sys.argv.index("--selftest") + 1:]
    out = args[0] if args else os.path.join(_tf.gettempdir(), "converter_selftest.log")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    # A windowed build (console=False, or pythonw.exe) has sys.stdout set to
    # None, so a bare print raises AttributeError here and the process would
    # exit non-zero with the log already reporting PASSED. The log file is the
    # real output; echoing it is best effort.
    report = "\n".join(lines) + "\nselftest log: " + out
    try:
        print(report)
    except (AttributeError, OSError, ValueError):
        pass

    return not any(l.startswith("SELFTEST FAILED") for l in lines)


# The selftest must be runnable where there is no display and no tkinter: a CI
# runner, or a fresh Linux box before python3-tk is installed. So it runs and
# exits here, above the GUI imports, rather than from main().
if __name__ == "__main__" and "--selftest" in sys.argv:
    sys.exit(0 if _selftest() else 1)


import tkinter as tk  # noqa: E402
from tkinter import ttk, filedialog, messagebox  # noqa: E402


# --- Palette (pulled from martinworks.css) -----------------------------------
BG = "#141210"          # page background
PANEL = "#1c1814"       # card / panel background
PANEL_HOVER = "#221e18"
LINE = "#3a3028"        # hairlines / borders
ACCENT = "#c8922a"      # primary gold
ACCENT_HOVER = "#e8b44a"  # bright gold
GOLD_MID = "#7a5518"    # decorative gold
GOLD_TAG = "#b3893a"    # readable gold (small labels)
TEXT = "#e8dfc8"        # primary text (parchment)
MUTED = "#a8987a"       # secondary text
DIM = "#988b6c"         # dim text
DROP_IDLE = LINE
DROP_HOVER = ACCENT
OK = "#e8b44a"          # success (gold)
ERR = "#d9663f"         # failure (warm red)

# --- Fonts (set by configure_fonts at startup) -------------------------------
HEAD_FONT = "Georgia"     # Cinzel once loaded
HEAD_BLACK = "Georgia"    # Cinzel Black once loaded
BODY_FONT = "Georgia"     # Crimson Pro once loaded


def tracked(text, space=" "):
    """Simulate CSS letter-spacing (Tk has none) by inserting thin spaces."""
    return space.join(text)


def configure_fonts(root):
    """Privately load the bundled Cinzel / Crimson Pro fonts and pick families."""
    global HEAD_FONT, HEAD_BLACK, BODY_FONT
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    fdir = os.path.join(base, "fonts")
    if sys.platform == "win32" and os.path.isdir(fdir):
        try:
            import ctypes
            gdi32 = ctypes.windll.gdi32
            gdi32.AddFontResourceExW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]
            for ttf in glob.glob(os.path.join(fdir, "*.ttf")):
                gdi32.AddFontResourceExW(ttf, 0x10, None)  # FR_PRIVATE
        except Exception:
            pass
    elif os.path.isdir(fdir):
        # Linux/BSD. There is no private-font API here, so the closest
        # equivalent is a per-user fontconfig dir: visible to this user only,
        # never system-wide, and no root needed. Copy once, then fc-cache.
        try:
            import shutil
            import subprocess
            dest = os.path.join(
                os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
                "fonts", "martinworks-converter",
            )
            os.makedirs(dest, exist_ok=True)
            copied = False
            for ttf in glob.glob(os.path.join(fdir, "*.ttf")):
                target = os.path.join(dest, os.path.basename(ttf))
                if not os.path.exists(target):
                    shutil.copy2(ttf, target)
                    copied = True
            if copied:
                # Without this fontconfig will not see them until it rescans,
                # so the first run would silently fall back.
                subprocess.run(["fc-cache", "-f", dest],
                               capture_output=True, timeout=30, check=False)
        except Exception:
            pass
    try:
        import tkinter.font as tkfont
        fams = set(tkfont.families(root))
    except Exception:
        fams = set()
    if "Cinzel" in fams:
        HEAD_FONT = "Cinzel"
    elif "Constantia" in fams:
        HEAD_FONT = "Constantia"
    HEAD_BLACK = "Cinzel Black" if "Cinzel Black" in fams else HEAD_FONT
    if "Crimson Pro" in fams:
        BODY_FONT = "Crimson Pro"
    elif BODY_FONT not in fams:
        # Georgia ships with Windows and is not guaranteed on Linux, so fall
        # through to serifs that actually exist there before Tk picks Helvetica.
        for candidate in ("Georgia", "Liberation Serif", "DejaVu Serif",
                          "Nimbus Roman", "FreeSerif"):
            if candidate in fams:
                BODY_FONT = candidate
                break
    if HEAD_FONT not in fams:
        for candidate in ("Georgia", "Liberation Serif", "DejaVu Serif",
                          "Nimbus Roman", "FreeSerif"):
            if candidate in fams:
                HEAD_FONT = HEAD_BLACK = candidate
                break


# --- Image conversion engine -------------------------------------------------
# Lives in image_engine so it can be imported and tested without a GUI toolkit.


# --- Reusable file-queue panel (drop zone + list) ----------------------------

class FileQueuePanel(ttk.Frame):
    """Drop zone + file list + Browse/Add-Folder/Clear, shared by both tabs."""

    def __init__(self, parent, root, extensions, dnd_hint, browse_title):
        super().__init__(parent, style="TFrame")
        self.root = root
        self.extensions = {e.lower() for e in extensions}
        self.browse_title = browse_title
        self.files = []
        self.recurse = tk.BooleanVar(value=True)
        self.status_cb = None

        # Drop zone
        self.drop = tk.Frame(self, bg=PANEL, highlightthickness=1,
                             highlightbackground=DROP_IDLE, height=120)
        self.drop.pack(fill="x")
        self.drop.pack_propagate(False)
        hint = dnd_hint if DND_AVAILABLE else "Use Browse or Add Folder below"
        self.drop_label = tk.Label(self.drop, text=f"⤓   {hint}", bg=PANEL, fg=MUTED,
                                   font=(BODY_FONT, 14))
        self.drop_label.pack(expand=True)
        sub = tk.Label(self.drop, text=tracked("FILES AND WHOLE FOLDERS ACCEPTED"),
                       bg=PANEL, fg=GOLD_TAG, font=(HEAD_FONT, 8))
        sub.pack(pady=(0, 14))
        if DND_AVAILABLE:
            for w in (self.drop, self.drop_label, sub):
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", self._on_drop)
                w.dnd_bind("<<DropEnter>>", lambda e: self._set_active(True))
                w.dnd_bind("<<DropLeave>>", lambda e: self._set_active(False))

        # Buttons row
        row = ttk.Frame(self, style="TFrame")
        row.pack(fill="x", pady=(12, 0))
        self.count_label = ttk.Label(row, text="No files queued", style="Muted.TLabel")
        self.count_label.pack(side="left")
        ttk.Checkbutton(row, text="Include subfolders", variable=self.recurse,
                        style="TCheckbutton").pack(side="left", padx=(14, 0))
        ttk.Button(row, text="Clear", style="Ghost.TButton", command=self.clear).pack(side="right")
        ttk.Button(row, text="Add Folder", style="Ghost.TButton",
                   command=self._browse_folder).pack(side="right", padx=(0, 6))
        ttk.Button(row, text="Browse", style="Ghost.TButton",
                   command=self._browse).pack(side="right", padx=(0, 6))

        # File list
        lf = tk.Frame(self, bg=PANEL, highlightthickness=1, highlightbackground=LINE)
        lf.pack(fill="both", expand=True, pady=(8, 0))
        sb = ttk.Scrollbar(lf)
        sb.pack(side="right", fill="y")
        self.listbox = tk.Listbox(lf, bg=PANEL, fg=TEXT, height=6, selectbackground=GOLD_MID,
                                  selectforeground=TEXT, relief="flat", highlightthickness=0,
                                  font=(BODY_FONT, 12), yscrollcommand=sb.set, activestyle="none",
                                  borderwidth=0)
        self.listbox.pack(side="left", fill="both", expand=True, padx=2, pady=2)
        sb.config(command=self.listbox.yview)

    def _status(self, text):
        if self.status_cb:
            self.status_cb(text)

    def _set_active(self, active):
        self.drop.config(highlightbackground=DROP_HOVER if active else DROP_IDLE,
                         highlightthickness=2 if active else 1)
        self.drop_label.config(fg=TEXT if active else MUTED)

    def _on_drop(self, event):
        self._set_active(False)
        self.add_paths(self.root.tk.splitlist(event.data))

    def add_paths(self, paths):
        added = 0
        recurse = self.recurse.get()
        for p in paths:
            p = p.strip()
            if not p:
                continue
            if os.path.isdir(p):
                for f in self._iter_folder(p, recurse):
                    added += self._queue_one(f)
            elif os.path.isfile(p):
                added += self._queue_one(p)
        self.update_count()
        self._status(f"Added {added} file(s)" if added else "No new files found")

    def _queue_one(self, path):
        if os.path.splitext(path)[1].lower() not in self.extensions:
            return 0
        if path in self.files:
            return 0
        self.files.append(path)
        self.listbox.insert("end", "   " + os.path.basename(path))
        self.listbox.itemconfig("end", foreground=TEXT)
        return 1

    @staticmethod
    def _iter_folder(folder, recurse):
        if recurse:
            for dirpath, _dirs, names in os.walk(folder):
                for n in sorted(names):
                    yield os.path.join(dirpath, n)
        else:
            for n in sorted(os.listdir(folder)):
                full = os.path.join(folder, n)
                if os.path.isfile(full):
                    yield full

    def _browse(self):
        patterns = ";".join("*" + e for e in sorted(self.extensions))
        paths = filedialog.askopenfilenames(
            title=self.browse_title,
            filetypes=[("Supported files", patterns), ("All files", "*.*")])
        if paths:
            self.add_paths(paths)

    def _browse_folder(self):
        d = filedialog.askdirectory(title="Select a folder")
        if d:
            self.add_paths([d])

    def clear(self):
        self.files.clear()
        self.listbox.delete(0, "end")
        self.update_count()
        self._status("Cleared")

    def update_count(self):
        n = len(self.files)
        self.count_label.config(text="No files queued" if n == 0 else f"{n} file(s) queued")

    def update_row(self, idx, text, color):
        if idx < self.listbox.size():
            self.listbox.delete(idx)
            self.listbox.insert(idx, "   " + text)
            self.listbox.itemconfig(idx, foreground=color)


# --- Application -------------------------------------------------------------

class ConverterApp:
    def __init__(self, root):
        self.root = root
        root.title("MartinWorks Converter")
        root.geometry("640x740")
        root.minsize(560, 660)
        root.configure(bg=BG)

        self._build_styles()
        self._build_topbar(root)

        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True, padx=14, pady=(2, 12))
        img_tab = ttk.Frame(nb, style="TFrame", padding=14)
        doc_tab = ttk.Frame(nb, style="TFrame", padding=14)
        nb.add(img_tab, text=tracked("IMAGES", " "))
        nb.add(doc_tab, text=tracked("DOCUMENTS", " "))

        self._build_image_tab(img_tab)
        self._build_document_tab(doc_tab)

    # thin gold gradient accent bar across the top (mirrors site .topbar)
    def _build_topbar(self, root):
        bar = tk.Canvas(root, height=3, highlightthickness=0, bd=0, bg=BG)
        bar.pack(fill="x", side="top")

        def hex_to_rgb(h):
            return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))

        stops = [(0.0, BG), (0.25, GOLD_MID), (0.5, ACCENT), (0.75, GOLD_MID), (1.0, BG)]
        rgb_stops = [(p, hex_to_rgb(c)) for p, c in stops]

        def color_at(t):
            for i in range(len(rgb_stops) - 1):
                p0, c0 = rgb_stops[i]
                p1, c1 = rgb_stops[i + 1]
                if p0 <= t <= p1:
                    f = 0 if p1 == p0 else (t - p0) / (p1 - p0)
                    return tuple(round(c0[j] + (c1[j] - c0[j]) * f) for j in range(3))
            return rgb_stops[-1][1]

        def draw(_=None):
            bar.delete("g")
            w = bar.winfo_width()
            if w < 2:
                return
            for x in range(w):
                r, g, b = color_at(x / (w - 1))
                bar.create_line(x, 0, x, 3, fill=f"#{r:02x}{g:02x}{b:02x}", tags="g")

        bar.bind("<Configure>", draw)

    def _build_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=TEXT, font=(BODY_FONT, 12))
        style.configure("Title.TLabel", background=BG, foreground=TEXT, font=(HEAD_BLACK, 20))
        style.configure("Eyebrow.TLabel", background=BG, foreground=ACCENT, font=(HEAD_FONT, 9))
        style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=(BODY_FONT, 11))
        style.configure("Lead.TLabel", background=BG, foreground=MUTED, font=(BODY_FONT, 11, "italic"))

        # primary (gold) button
        style.configure("Accent.TButton", font=(HEAD_FONT, 11), padding=(10, 10),
                        background=ACCENT, foreground=BG, borderwidth=0, relief="flat")
        style.map("Accent.TButton",
                  background=[("active", ACCENT_HOVER), ("disabled", LINE)],
                  foreground=[("disabled", DIM)])

        # secondary (outline / ghost) button
        style.configure("Ghost.TButton", font=(HEAD_FONT, 9), padding=(12, 6),
                        background=PANEL, foreground=GOLD_TAG, borderwidth=1, relief="flat")
        style.map("Ghost.TButton",
                  background=[("active", ACCENT)],
                  foreground=[("active", BG)],
                  bordercolor=[("!active", LINE), ("active", ACCENT)])

        style.configure("TCombobox", padding=5, fieldbackground=PANEL, background=PANEL,
                        foreground=TEXT, arrowcolor=ACCENT, bordercolor=LINE,
                        selectbackground=PANEL, selectforeground=TEXT)
        style.map("TCombobox", fieldbackground=[("readonly", PANEL)],
                  foreground=[("readonly", TEXT)], arrowcolor=[("active", ACCENT_HOVER)])

        style.configure("TEntry", fieldbackground=PANEL, foreground=TEXT,
                        bordercolor=LINE, insertcolor=ACCENT, padding=4)

        style.configure("TRadiobutton", background=BG, foreground=MUTED, font=(BODY_FONT, 12))
        style.map("TRadiobutton", background=[("active", BG)],
                  foreground=[("selected", TEXT), ("active", TEXT)],
                  indicatorcolor=[("selected", ACCENT), ("!selected", LINE)])

        style.configure("TCheckbutton", background=BG, foreground=MUTED, font=(BODY_FONT, 11))
        style.map("TCheckbutton", background=[("active", BG)],
                  foreground=[("active", TEXT)],
                  indicatorcolor=[("selected", ACCENT), ("!selected", PANEL)])

        style.configure("Horizontal.TScale", background=BG, troughcolor=PANEL)

        style.configure("Vertical.TScrollbar", background=PANEL_HOVER, troughcolor=BG,
                        bordercolor=LINE, arrowcolor=MUTED, relief="flat", borderwidth=0)
        style.map("Vertical.TScrollbar",
                  background=[("active", GOLD_MID), ("!active", PANEL_HOVER)],
                  arrowcolor=[("active", ACCENT)])

        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=BG, foreground=DIM,
                        padding=(20, 9), font=(HEAD_FONT, 10), borderwidth=0)
        style.map("TNotebook.Tab",
                  background=[("selected", BG)],
                  foreground=[("selected", ACCENT), ("active", MUTED)])

    # eyebrow + title header used by both tabs
    def _build_header(self, tab, eyebrow, title):
        ttk.Label(tab, text="✦  " + tracked(eyebrow, " "),
                  style="Eyebrow.TLabel").pack(anchor="w")
        ttk.Label(tab, text=title, style="Title.TLabel").pack(anchor="w", pady=(3, 12))

    # shared output-destination block
    def _build_output_dest(self, parent, mode_var, dir_var):
        dest = ttk.Frame(parent, style="TFrame")
        dest.pack(fill="x", pady=(10, 0))
        ttk.Radiobutton(dest, text="Save next to original", value="same",
                        variable=mode_var).pack(anchor="w")
        row = ttk.Frame(dest, style="TFrame")
        row.pack(fill="x", anchor="w")
        ttk.Radiobutton(row, text="Save to folder:", value="folder",
                        variable=mode_var).pack(side="left")
        entry = ttk.Entry(row, textvariable=dir_var)
        entry.pack(side="left", fill="x", expand=True, padx=(8, 6))
        btn = ttk.Button(row, text="...", style="Ghost.TButton", width=3,
                         command=lambda: self._choose_dir(mode_var, dir_var))
        btn.pack(side="left")

        def sync(*_):
            on = mode_var.get() == "folder"
            entry.state(["!disabled"] if on else ["disabled"])
            btn.state(["!disabled"] if on else ["disabled"])
        mode_var.trace_add("write", sync)
        sync()

    def _choose_dir(self, mode_var, dir_var):
        d = filedialog.askdirectory(title="Choose output folder")
        if d:
            dir_var.set(d)
            mode_var.set("folder")

    def _convert_label(self, text):
        return tracked("CONVERT", " ") + "   " + text

    # --- Images tab ---
    def _build_image_tab(self, tab):
        self._build_header(tab, "IMAGE CONVERSION", "Images")
        ttk.Label(tab, text="PNG · JPG · WebP · BMP · GIF · TIFF · ICO · SVG in",
                  style="Lead.TLabel").pack(anchor="w", pady=(0, 10))

        self.img_panel = FileQueuePanel(tab, self.root, IMAGE_EXTENSIONS,
                                        "Drag & drop images or folders here", "Select images")
        self.img_panel.pack(fill="both", expand=True)

        self.img_format = tk.StringVar(value="PNG")
        self.img_quality = tk.IntVar(value=90)
        # StringVar, not IntVar: an IntVar raises on any non-numeric keystroke.
        self.img_svg_width = tk.StringVar(value="0")
        self.img_output_mode = tk.StringVar(value="same")
        self.img_output_dir = tk.StringVar(value="")

        opts = ttk.Frame(tab, style="TFrame")
        opts.pack(fill="x", pady=(14, 0))
        ttk.Label(opts, text="Convert to").grid(row=0, column=0, sticky="w", pady=4)
        fmt = ttk.Combobox(opts, textvariable=self.img_format, state="readonly",
                           values=list(FORMATS.keys()), width=10)
        fmt.grid(row=0, column=1, sticky="w", padx=(10, 0))
        fmt.bind("<<ComboboxSelected>>", lambda e: self._sync_quality())
        ttk.Label(opts, text="Quality").grid(row=0, column=2, sticky="e", padx=(24, 0))
        self.img_quality_scale = ttk.Scale(opts, from_=1, to=100, variable=self.img_quality,
                                           command=lambda v: self.img_quality_value.config(
                                               text=str(self.img_quality.get())))
        self.img_quality_scale.grid(row=0, column=3, sticky="ew", padx=(10, 0))
        self.img_quality_value = ttk.Label(opts, text="90", style="Muted.TLabel", width=4)
        self.img_quality_value.grid(row=0, column=4, sticky="w")
        opts.columnconfigure(3, weight=1)

        # SVG has no pixel size of its own until something renders it, so the
        # width is the one setting that decides what a converted SVG looks like.
        ttk.Label(opts, text="SVG width").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Spinbox(opts, from_=0, to=16384, increment=64, width=8,
                    textvariable=self.img_svg_width).grid(row=1, column=1, sticky="w",
                                                          padx=(10, 0))
        if SVG_AVAILABLE:
            svg_hint = "px. 0 keeps the size in the file. Applies to SVG input only."
        else:
            svg_hint = "SVG conversion unavailable here: " + (SVG_ERROR or "")
        ttk.Label(opts, text=svg_hint, style="Muted.TLabel",
                  wraplength=420).grid(row=1, column=2, columnspan=3, sticky="w",
                                       padx=(24, 0))

        self._build_output_dest(tab, self.img_output_mode, self.img_output_dir)

        self.img_convert_btn = ttk.Button(
            tab, text=self._convert_label("IMAGES"), style="Accent.TButton",
            command=lambda: self._run_jobs(
                self.img_panel,
                lambda s, o: convert_image(s, self.img_format.get(), self.img_quality.get(), o,
                                           svg_width=self._svg_width()),
                self.img_format.get(), self.img_status, self.img_convert_btn,
                self.img_output_mode, self.img_output_dir))
        self.img_convert_btn.pack(fill="x", pady=(16, 6))
        self.img_status = ttk.Label(tab, text="Ready", style="Lead.TLabel")
        self.img_status.pack(anchor="w")
        self.img_panel.status_cb = lambda t: self.img_status.config(text=t)
        self._sync_quality()

    def _svg_width(self):
        """The SVG width box as an int. Anything unparseable means native size."""
        try:
            value = int(float(self.img_svg_width.get().strip()))
        except (ValueError, AttributeError):
            return 0
        return max(0, min(value, 16384))

    def _sync_quality(self):
        on = self.img_format.get() in QUALITY_FORMATS
        self.img_quality_scale.state(["!disabled"] if on else ["disabled"])
        self.img_quality_value.config(text=str(self.img_quality.get()))

    # --- Documents tab ---
    def _build_document_tab(self, tab):
        self._build_header(tab, "DOCUMENT CONVERSION", "Documents")
        ttk.Label(tab, text="PDF · DOCX · TXT · HTML · Markdown · RTF",
                  style="Lead.TLabel").pack(anchor="w", pady=(0, 10))

        if not DOC_AVAILABLE:
            ttk.Label(tab, text="Document conversion is unavailable.",
                      style="TLabel").pack(anchor="w", pady=(20, 4))
            ttk.Label(tab, text=f"Import error: {DOC_IMPORT_ERROR}",
                      style="Muted.TLabel", wraplength=560).pack(anchor="w")
            return

        exts = list(doc_converter.DOC_FORMATS.keys())
        self.doc_panel = FileQueuePanel(tab, self.root, exts,
                                        "Drag & drop documents or folders here", "Select documents")
        self.doc_panel.pack(fill="both", expand=True)

        self.doc_format = tk.StringVar(value="PDF")
        self.doc_output_mode = tk.StringVar(value="same")
        self.doc_output_dir = tk.StringVar(value="")

        opts = ttk.Frame(tab, style="TFrame")
        opts.pack(fill="x", pady=(14, 0))
        ttk.Label(opts, text="Convert to").grid(row=0, column=0, sticky="w", pady=4)
        labels = [lbl for lbl, _ext in doc_converter.TARGET_FORMATS]
        ttk.Combobox(opts, textvariable=self.doc_format, state="readonly",
                     values=labels, width=12).grid(row=0, column=1, sticky="w", padx=(10, 0))

        self._build_output_dest(tab, self.doc_output_mode, self.doc_output_dir)

        self.doc_convert_btn = ttk.Button(
            tab, text=self._convert_label("DOCUMENTS"), style="Accent.TButton",
            command=lambda: self._run_jobs(
                self.doc_panel,
                lambda s, o: doc_converter.convert_document(s, self._doc_ext(), o),
                self.doc_format.get(), self.doc_status, self.doc_convert_btn,
                self.doc_output_mode, self.doc_output_dir))
        self.doc_convert_btn.pack(fill="x", pady=(16, 6))
        self.doc_status = ttk.Label(tab, text="Ready", style="Lead.TLabel")
        self.doc_status.pack(anchor="w")
        self.doc_panel.status_cb = lambda t: self.doc_status.config(text=t)

    def _doc_ext(self):
        label = self.doc_format.get()
        for lbl, ext in doc_converter.TARGET_FORMATS:
            if lbl == label:
                return ext
        return ".pdf"

    # --- shared conversion runner ---
    def _run_jobs(self, panel, convert_fn, label, status_label, convert_btn, mode_var, dir_var):
        if not panel.files:
            messagebox.showinfo("Nothing to convert", "Add one or more files first.")
            return
        if mode_var.get() == "folder":
            d = dir_var.get().strip()
            if not d or not os.path.isdir(d):
                messagebox.showwarning("Output folder", "Pick a valid output folder.")
                return
        convert_btn.state(["disabled"])
        status_label.config(text="Converting...")
        threading.Thread(target=self._worker,
                         args=(panel, convert_fn, label, status_label, convert_btn,
                               mode_var, dir_var), daemon=True).start()

    def _worker(self, panel, convert_fn, label, status_label, convert_btn, mode_var, dir_var):
        mode = mode_var.get()
        out_dir = dir_var.get().strip()
        ok, fail, errors, total = 0, 0, [], 0
        for i, src in enumerate(list(panel.files)):
            try:
                dest_dir = out_dir if mode == "folder" else os.path.dirname(src)
                dest, size = convert_fn(src, dest_dir)
                total += size
                ok += 1
                self.root.after(0, panel.update_row, i,
                                f"✓   {os.path.basename(dest)}    -    {human_size(size)}", OK)
            except Exception as e:  # noqa: BLE001 - report per-file, keep going
                fail += 1
                errors.append(f"{os.path.basename(src)}: {e}")
                self.root.after(0, panel.update_row, i,
                                f"✗   {os.path.basename(src)}    -    {e}", ERR)
                traceback.print_exc()
        self.root.after(0, self._finish, label, status_label, convert_btn, ok, fail, errors, total)

    def _finish(self, label, status_label, convert_btn, ok, fail, errors, total):
        convert_btn.state(["!disabled"])
        msg = f"Done - {ok} converted ({human_size(total)} total)"
        if fail:
            msg += f", {fail} failed"
        status_label.config(text=msg)
        if fail:
            messagebox.showerror("Some conversions failed", "\n".join(errors[:10]))
        elif ok:
            messagebox.showinfo("Conversion complete",
                                f"Converted {ok} file(s) to {label}.\n"
                                f"Total output size: {human_size(total)}")


def _set_window_icon(root, base):
    """Window/taskbar icon. iconbitmap only understands .ico on Windows; on
    Linux Tk needs a PhotoImage via iconphoto, so use the PNG we already ship.
    The reference is kept on root or Tk garbage-collects it and the icon
    silently disappears."""
    try:
        if sys.platform == "win32":
            root.iconbitmap(os.path.join(base, "icon.ico"))
            return
        import tkinter as _tk
        png = os.path.join(base, "icon.png")
        if os.path.exists(png):
            root._icon_ref = _tk.PhotoImage(file=png)
            root.iconphoto(True, root._icon_ref)
    except Exception:
        pass


def main():
    root = TkinterDnD.Tk() if DND_AVAILABLE else tk.Tk()
    _base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    _set_window_icon(root, _base)
    configure_fonts(root)
    ConverterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

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

"""Tests for the conversion engine and for the shipped entry point.

These run headless on purpose: image_engine imports no tkinter, and the
--selftest path in image_converter.py exits before the GUI imports. So the
whole suite works on a CI runner with no display and no python3-tk.
"""

import os
import subprocess
import sys

import pytest
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import image_engine as eng  # noqa: E402

# 64x32 so a wrong rotation or a squashed aspect ratio is obvious in the size.
SVG = b"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="64" height="32" viewBox="0 0 64 32">
  <rect width="64" height="32" fill="#1b1b1b"/>
  <circle cx="16" cy="16" r="10" fill="#c9a227" fill-opacity="0.5"/>
</svg>
"""


@pytest.fixture
def svg_file(tmp_path):
    p = tmp_path / "sample.svg"
    p.write_bytes(SVG)
    return str(p)


@pytest.fixture
def png_file(tmp_path):
    p = tmp_path / "sample.png"
    Image.new("RGBA", (40, 20), (200, 160, 40, 128)).save(str(p))
    return str(p)


def test_version_matches_version_file():
    with open(os.path.join(ROOT, "VERSION"), encoding="utf-8") as fh:
        assert eng.__version__ == fh.read().strip()


def test_svg_is_input_only():
    """SVG is a raster target nobody can honour: do not let it into FORMATS."""
    assert "SVG" not in eng.FORMATS
    assert ".svg" in eng.IMAGE_EXTENSIONS


def test_quality_formats_are_real_targets():
    assert eng.QUALITY_FORMATS <= set(eng.FORMATS)


@pytest.mark.skipif(not eng.SVG_AVAILABLE, reason="no SVG backend installed")
def test_svg_to_png_keeps_native_size(svg_file, tmp_path):
    dest, size = eng.convert_image(svg_file, "PNG", 90, str(tmp_path))
    assert size > 0
    with Image.open(dest) as im:
        assert im.size == (64, 32)


@pytest.mark.skipif(not eng.SVG_AVAILABLE, reason="no SVG backend installed")
def test_svg_width_scales_and_preserves_aspect(svg_file, tmp_path):
    dest, _ = eng.convert_image(svg_file, "PNG", 90, str(tmp_path), svg_width=256)
    with Image.open(dest) as im:
        assert im.size == (256, 128)


@pytest.mark.skipif(not eng.SVG_AVAILABLE, reason="no SVG backend installed")
def test_svg_to_jpeg_flattens_alpha(svg_file, tmp_path):
    """JPEG has no alpha channel, so the transparent circle must be composited."""
    dest, _ = eng.convert_image(svg_file, "JPEG", 90, str(tmp_path))
    with Image.open(dest) as im:
        assert im.mode == "RGB"


@pytest.mark.skipif(not eng.SVG_AVAILABLE, reason="no SVG backend installed")
def test_gzipped_svg_is_detected_by_content_not_extension(tmp_path):
    """A .svg file that is really gzipped still has to work."""
    import gzip
    p = tmp_path / "packed.svg"
    p.write_bytes(gzip.compress(SVG))
    dest, _ = eng.convert_image(str(p), "PNG", 90, str(tmp_path))
    with Image.open(dest) as im:
        assert im.size == (64, 32)


def test_raster_roundtrip_and_alpha_flattening(png_file, tmp_path):
    dest, size = eng.convert_image(png_file, "JPEG", 85, str(tmp_path))
    assert size > 0
    with Image.open(dest) as im:
        assert im.mode == "RGB"
        assert im.size == (40, 20)


def test_unique_path_does_not_overwrite(tmp_path):
    p = tmp_path / "taken.png"
    p.write_bytes(b"x")
    assert eng.unique_path(str(p)) != str(p)


def test_human_size_is_readable():
    assert eng.human_size(0)
    assert "KB" in eng.human_size(2048) or "B" in eng.human_size(2048)


# --- negatives ---------------------------------------------------------------

def test_missing_file_raises(tmp_path):
    with pytest.raises(Exception):
        eng.convert_image(str(tmp_path / "nope.png"), "PNG", 90, str(tmp_path))


@pytest.mark.skipif(not eng.SVG_AVAILABLE, reason="no SVG backend installed")
def test_malformed_svg_raises(tmp_path):
    p = tmp_path / "broken.svg"
    p.write_bytes(b"<svg><this is not xml at all")
    with pytest.raises(Exception):
        eng.convert_image(str(p), "PNG", 90, str(tmp_path))


def test_unknown_target_format_raises(png_file, tmp_path):
    with pytest.raises(KeyError):
        eng.convert_image(png_file, "NOT_A_FORMAT", 90, str(tmp_path))


def test_prepare_windows_cairo_is_a_noop_off_windows():
    assert eng.CAIRO_DLL_DIR is None or sys.platform.startswith("win")


# --- the shipped entry point -------------------------------------------------

def test_shipped_entry_point_selftest_passes():
    """Run image_converter.py --selftest the way a user would, in a subprocess.

    This is the only test that exercises the real entry point, including the
    early exit that keeps --selftest above the tkinter imports.
    """
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "image_converter.py"), "--selftest"],
        capture_output=True, text=True, timeout=300, cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr

#!/usr/bin/env bash
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

# Launch the MartinWorks Converter on Linux.
# Mirrors "Image Converter.bat" on Windows, with the dependency checks that
# matter here: tkinter is a separate OS package on most distributions.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Prefer the project venv, so a working setup is not at the mercy of whatever
# the system python happens to have installed.
if [ -x "$HERE/.venv-converter/bin/python" ]; then
    PY="$HERE/.venv-converter/bin/python"
elif [ -x "$HERE/.venv/bin/python" ]; then
    PY="$HERE/.venv/bin/python"
else
    PY="$(command -v python3 || true)"
fi

if [ -z "$PY" ]; then
    fail "No python3 found on PATH."
fi

# Launched from a desktop shortcut there is no terminal, so anything written to
# stderr is invisible and the app just appears not to start. Show a dialog in
# that case and keep plain stderr when run from a shell.
fail() {
    local msg="$1"
    printf '%s\n' "$msg" >&2
    if [ ! -t 2 ]; then
        if command -v zenity >/dev/null 2>&1; then
            zenity --error --no-wrap --title="MartinWorks Converter" \
                   --text="$msg" >/dev/null 2>&1 || true
        elif command -v xmessage >/dev/null 2>&1; then
            xmessage -center "$msg" >/dev/null 2>&1 || true
        elif command -v notify-send >/dev/null 2>&1; then
            notify-send "MartinWorks Converter" "$msg" >/dev/null 2>&1 || true
        fi
    fi
    exit 1
}

tk_install_hint() {
    if command -v apt >/dev/null 2>&1;    then echo "sudo apt install python3-tk"
    elif command -v pacman >/dev/null 2>&1; then echo "sudo pacman -S tk"
    elif command -v dnf >/dev/null 2>&1;    then echo "sudo dnf install python3-tkinter"
    elif command -v zypper >/dev/null 2>&1; then echo "sudo zypper install python3-tk"
    else echo "install your distribution's python3 tkinter package"
    fi
}

# --install-desktop puts it in the application menu, same as muse.sh does, and
# drops a shortcut on the desktop.
if [ "${1:-}" = "--install-desktop" ]; then
    APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
    mkdir -p "$APPS"
    ENTRY="$APPS/martinworks-converter.desktop"
    cat > "$ENTRY" <<DESKTOP
[Desktop Entry]
Type=Application
Name=MartinWorks Converter
Comment=Convert images and documents
Exec=$HERE/image-converter.sh
Icon=$HERE/icon.png
Terminal=false
Categories=Graphics;2DGraphics;
DESKTOP
    chmod +x "$ENTRY"
    update-desktop-database "$APPS" >/dev/null 2>&1 || true
    echo "Menu entry:        $ENTRY"

    DESK="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
    [ -d "${DESK:-}" ] || DESK="$HOME/Desktop"
    if [ -d "$DESK" ]; then
        cp "$ENTRY" "$DESK/martinworks-converter.desktop"
        # Cinnamon, GNOME and Nemo refuse to run a launcher that is not both
        # executable and explicitly marked trusted.
        chmod +x "$DESK/martinworks-converter.desktop"
        gio set "$DESK/martinworks-converter.desktop" \
                metadata::trusted true >/dev/null 2>&1 || true
        echo "Desktop shortcut:  $DESK/martinworks-converter.desktop"
    else
        echo "No desktop folder found, skipped the desktop shortcut."
    fi
    exit 0
fi

if ! "$PY" -c "import tkinter" >/dev/null 2>&1; then
    fail "MartinWorks Converter needs tkinter, which is a separate OS package.

Run this once in a terminal:

    $(tk_install_hint)

A virtualenv cannot supply it: tkinter is a C extension built against the
system Tk, so it has to come from the distribution.

Conversion itself does not need tkinter. To check the engine without a GUI:
    $PY \"$HERE/image_converter.py\" --selftest"
fi

exec "$PY" "$HERE/image_converter.py" "$@"

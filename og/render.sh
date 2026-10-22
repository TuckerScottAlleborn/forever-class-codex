#!/usr/bin/env sh
# Renders og/card.html to ../og.png (1200x630) with headless Edge.
here="$(cd "$(dirname "$0")" && pwd)"
edge="/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
win() { cygpath -w "$1" 2>/dev/null || echo "$1"; }
"$edge" --headless=new --user-data-dir="$(win "${TMP:-/tmp}/og-edge-profile")" --no-first-run --disable-gpu --hide-scrollbars --force-device-scale-factor=1 \
  --window-size=1200,630 --virtual-time-budget=5000 \
  --screenshot="$(win "$here/../og.png")" "file:///$(win "$here/card.html" | tr '\\' '/')"

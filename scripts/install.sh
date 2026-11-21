#!/usr/bin/env bash
# Install the Aqua-session WebKit kiosk on THIS Mac (run logged-in as the GUI user).
set -euo pipefail

PREFIX="${HOME}/.local/mac-kiosk-display"
SRC="$(cd "$(dirname "$0")/.." && pwd)"
PY="${KIOSK_PYTHON:-/usr/local/bin/python3}"
[ -x "$PY" ] || PY="$(command -v python3)"

mkdir -p "$PREFIX/scripts" "$HOME/Library/LaunchAgents" "$HOME/Library/Logs" "$HOME/bin"
cp -f "$SRC/scripts/kiosk_server.py" "$SRC/scripts/kiosk_ui.py" "$SRC/scripts/kiosk_lib.py" "$PREFIX/scripts/"
cp -f "$SRC/scripts/kiosk-ctl" "$PREFIX/scripts/"
chmod +x "$PREFIX/scripts/kiosk-ctl" "$PREFIX/scripts/kiosk_server.py"
ln -sfn "$PREFIX/scripts/kiosk-ctl" "$HOME/bin/kiosk-ctl"

if [ ! -x "$PREFIX/venv/bin/python3" ]; then
  "$PY" -m venv "$PREFIX/venv"
fi
"$PREFIX/venv/bin/pip" install -q --upgrade pip
"$PREFIX/venv/bin/pip" install -q pyobjc-framework-Cocoa pyobjc-framework-WebKit

plist_src="$SRC/launchd/com.mac-kiosk-display.plist"
plist_dst="$HOME/Library/LaunchAgents/com.mac-kiosk-display.plist"
sed "s|HOME_PLACEHOLDER|${HOME}|g" "$plist_src" > "$plist_dst"

uid="$(id -u)"
launchctl bootout "gui/${uid}/com.mac-kiosk-display" 2>/dev/null || true
launchctl bootstrap "gui/${uid}" "$plist_dst"
launchctl enable "gui/${uid}/com.mac-kiosk-display" 2>/dev/null || true
launchctl kickstart -k "gui/${uid}/com.mac-kiosk-display" 2>/dev/null || true

# wait for HTTP over the unix socket
ok=0
sock="$HOME/.local/state/mac-kiosk-display/kiosk.sock"
for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
  if curl -fsS --unix-socket "$sock" --max-time 1 "http://kiosk/health" >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 0.4
done

echo "installed prefix=$PREFIX plist=$plist_dst"
if [ "$ok" = 1 ]; then
  echo "health: ok"
  curl -fsS --unix-socket "$sock" "http://kiosk/health"; echo
else
  echo "health: not up yet — check $HOME/Library/Logs/mac-kiosk-display.log" >&2
  tail -n 30 "$HOME/Library/Logs/mac-kiosk-display.log" 2>/dev/null || true
  exit 1
fi

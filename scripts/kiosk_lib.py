#!/usr/bin/env python3
"""Shared helpers for mac-kiosk-display (no AppKit)."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse

STATE_DIR = Path.home() / ".local" / "state" / "mac-kiosk-display"
CMD_FILE = STATE_DIR / "cmd.json"
STATE_FILE = STATE_DIR / "state.json"
UI_PID_FILE = STATE_DIR / "ui.pid"
CAFF_PID_FILE = STATE_DIR / "caffeinate.pid"
SOCK_PATH = STATE_DIR / "kiosk.sock"
DISPLAY_FILE = STATE_DIR / "display.json"


def log(msg: str) -> None:
    print(time.strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)


def write_json(path: Path, data: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def read_json(path: Path, default: dict | None = None) -> dict:
    if not path.exists():
        return {} if default is None else default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {} if default is None else default


def parse_until(value: str | None) -> int | None:
    if not value:
        return None
    value = value.strip().lower()
    now = time.localtime()
    if value in {"tonight", "end-of-day", "eod"}:
        return int(time.mktime((now.tm_year, now.tm_mon, now.tm_mday, 23, 59, 0, 0, 0, -1)))
    if value.isdigit():
        n = int(value)
        if n > 1_000_000_000:
            return n
        return int(time.time()) + n
    if ":" in value and len(value) <= 5:
        hh, mm = value.split(":", 1)
        end = time.mktime((now.tm_year, now.tm_mon, now.tm_mday, int(hh), int(mm), 0, 0, 0, -1))
        if end <= time.time():
            end += 86400
        return int(end)
    return None


def to_url(raw: str) -> tuple[str, str | None]:
    raw = raw.strip()
    parsed = urlparse(raw)
    if parsed.scheme in {"http", "https", "file"}:
        return raw, None
    path = str(Path(raw).expanduser().resolve())
    if not Path(path).exists():
        raise FileNotFoundError(path)
    return Path(path).as_uri(), path


def stop_pidfile(path: Path) -> None:
    if not path.exists():
        return
    try:
        pid = int(path.read_text().strip())
    except ValueError:
        path.unlink(missing_ok=True)
        return
    try:
        os.kill(pid, 15)
    except OSError:
        pass
    path.unlink(missing_ok=True)


def start_caffeinate(seconds: int | None) -> None:
    stop_pidfile(CAFF_PID_FILE)
    # -d: no idle display sleep while a page is shown (the page may still ask for display_sleep)
    # -i: no idle system sleep either, so the page keeps running while the panel is dark
    cmd = ["/usr/bin/caffeinate", "-d", "-i", "-u"]
    if seconds and seconds > 0:
        cmd.extend(["-t", str(int(seconds))])
    import subprocess

    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    write_json(STATE_DIR / "caff.json", {"pid": proc.pid})
    CAFF_PID_FILE.write_text(str(proc.pid), encoding="utf-8")


def wake_display() -> None:
    import subprocess

    subprocess.run(["/usr/bin/caffeinate", "-u", "-t", "3"], check=False)


def sleep_display() -> None:
    """Put the panel to sleep now. caffeinate -d only prevents *idle* sleep, so this sticks
    until wake_display() or real user input."""
    import subprocess

    subprocess.run(["/usr/bin/pmset", "displaysleepnow"], check=False)


def display_power_state() -> int | None:
    """IODisplayWrangler power state: 4 = on, 1 = asleep. None when unreadable."""
    import re
    import subprocess

    out = subprocess.run(
        ["/usr/sbin/ioreg", "-n", "IODisplayWrangler", "-r", "-d1"],
        capture_output=True, text=True, check=False,
    ).stdout
    m = re.search(r'"CurrentPowerState"=(\d)', out)
    return int(m.group(1)) if m else None

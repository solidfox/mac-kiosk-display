#!/usr/bin/env python3
"""Localhost HTTP control plane. Does not import AppKit (avoids GIL stall)."""
from __future__ import annotations

import json
import os
import socket
import socketserver
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from kiosk_lib import (
    CAFF_PID_FILE,
    CMD_FILE,
    SOCK_PATH,
    STATE_FILE,
    UI_PID_FILE,
    log,
    parse_until,
    read_json,
    start_caffeinate,
    stop_pidfile,
    to_url,
    wake_display,
    write_json,
)

TOKEN = os.environ.get("KIOSK_TOKEN", "")
HERE = Path(__file__).resolve().parent
UI_SCRIPT = HERE / "kiosk_ui.py"
PY = sys.executable


def _ui_alive() -> bool:
    if not UI_PID_FILE.exists():
        return False
    try:
        pid = int(UI_PID_FILE.read_text().strip())
        os.kill(pid, 0)
        return True
    except (ValueError, OSError):
        return False


def _ensure_ui() -> None:
    if _ui_alive():
        return
    log("starting ui process")
    logf = Path.home() / "Library" / "Logs" / "mac-kiosk-ui.log"
    logf.parent.mkdir(parents=True, exist_ok=True)
    lf = open(logf, "ab", buffering=0)
    proc = subprocess.Popen(
        [PY, "-u", str(UI_SCRIPT)],
        stdout=lf,
        stderr=lf,
        start_new_session=True,
    )
    UI_PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    UI_PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    time.sleep(0.3)


def _push_cmd(action: str, **extra) -> dict:
    cmd = {"action": action, "ts": time.time(), **extra}
    write_json(CMD_FILE, cmd)
    return cmd


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        log("http " + (fmt % args))

    def _auth_ok(self) -> bool:
        if not TOKEN:
            return True
        got = self.headers.get("Authorization", "")
        return got == f"Bearer {TOKEN}" or self.headers.get("X-Kiosk-Token") == TOKEN

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8")) if raw else {}

    def do_GET(self) -> None:  # noqa: N802
        if not self._auth_ok():
            self._json(401, {"error": "unauthorized"})
            return
        if self.path in {"/health", "/"}:
            self._json(200, {"ok": True, "service": "mac-kiosk-display", "ui": _ui_alive()})
            return
        if self.path == "/status":
            state = read_json(STATE_FILE, {"showing": False})
            state["ui"] = _ui_alive()
            state["socket"] = str(SOCK_PATH)
            state["pid"] = os.getpid()
            self._json(200, state)
            return
        self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if not self._auth_ok():
            self._json(401, {"error": "unauthorized"})
            return
        try:
            data = self._read_json()
        except json.JSONDecodeError:
            self._json(400, {"error": "bad_json"})
            return
        if self.path == "/wake":
            wake_display()
            self._json(200, {"ok": True, "woke": True})
            return
        if self.path == "/show":
            target = data.get("url") or data.get("path") or data.get("file")
            if not target:
                self._json(400, {"error": "url required"})
                return
            try:
                url, local = to_url(str(target))
            except FileNotFoundError as exc:
                self._json(404, {"error": f"missing {exc}"})
                return
            until = parse_until(data.get("until"))
            secs = None if until is None else max(1, until - int(time.time()))
            wake_display()
            start_caffeinate(secs)
            _ensure_ui()
            _push_cmd("show", url=url, local=local, until=until)
            state = {
                "showing": True,
                "url": url,
                "until": until,
                "until_human": time.strftime("%H:%M", time.localtime(until)) if until else None,
            }
            write_json(STATE_FILE, state)
            log(f"show {url} until={state['until_human']}")
            self._json(200, state)
            return
        if self.path == "/clear":
            stop_pidfile(CAFF_PID_FILE)
            _push_cmd("clear")
            write_json(STATE_FILE, {"showing": False})
            log("clear")
            self._json(200, {"showing": False})
            return
        if self.path == "/dismiss":
            _ensure_ui()
            _push_cmd("dismiss")
            self._json(200, {"ok": True, "dismiss": "queued"})
            return
        if self.path == "/snapshot":
            dest = data.get("path") or str(
                Path.home() / ".local/state/mac-kiosk-display/webview.png"
            )
            _ensure_ui()
            _push_cmd("snapshot", path=dest)
            self._json(200, {"ok": True, "path": dest})
            return
        self._json(404, {"error": "not_found"})


def main() -> None:
    SOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    if SOCK_PATH.exists():
        SOCK_PATH.unlink()

    class ThreadingUnixHTTPServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
        daemon_threads = True
        allow_reuse_address = True

    httpd = ThreadingUnixHTTPServer(str(SOCK_PATH), Handler)
    os.chmod(SOCK_PATH, 0o600)
    log(f"listening on unix:{SOCK_PATH}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()

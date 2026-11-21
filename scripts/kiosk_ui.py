#!/usr/bin/env python3
"""Aqua WKWebView kiosk. Polls cmd.json via NSTimer (no Python HTTP thread)."""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from AppKit import (
    NSApplication,
    NSBackingStoreBuffered,
    NSColor,
    NSScreen,
    NSTimer,
    NSWindow,
    NSWindowStyleMaskBorderless,
    NSApplicationPresentationHideDock,
    NSApplicationPresentationHideMenuBar,
)
import objc
from Foundation import NSObject, NSURL, NSURLRequest
from PyObjCTools import AppHelper
from WebKit import WKWebView, WKWebViewConfiguration

from kiosk_lib import (
    CMD_FILE,
    DISPLAY_FILE,
    STATE_FILE,
    log,
    read_json,
    sleep_display,
    wake_display,
    write_json,
)

SCREENSAVER_LEVEL = 1000
APPS = ("Preview", "Safari", "System Settings", "Google Chrome", "Chromium")
# A page that asked for the panel to sleep must say so again within this time, or the panel
# wakes on its own: a wedged page never leaves the kitchen dark.
DISPLAY_OFF_RENEW_S = 15 * 60
BRIDGE_NAME = "kiosk"  # window.webkit.messageHandlers.kiosk.postMessage({display: "on"|"off"})


class KioskUI(NSObject, protocols=[objc.protocolNamed("WKScriptMessageHandler")]):
    window = None
    webview = None
    last_ts = 0.0
    display_on = True
    display_asked_at = 0.0

    def applicationDidFinishLaunching_(self, _n):
        screen = NSScreen.mainScreen().frame()
        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            screen, NSWindowStyleMaskBorderless, NSBackingStoreBuffered, False
        )
        win.setTitle_("Kiosk Display")
        win.setOpaque_(True)
        win.setBackgroundColor_(NSColor.blackColor())
        win.setReleasedWhenClosed_(False)
        win.setCollectionBehavior_(1 << 0)
        win.setLevel_(SCREENSAVER_LEVEL)
        win.orderOut_(None)
        config = WKWebViewConfiguration.alloc().init()
        config.userContentController().addScriptMessageHandler_name_(self, BRIDGE_NAME)
        view = WKWebView.alloc().initWithFrame_configuration_(screen, config)
        win.setContentView_(view)
        self.window = win
        self.webview = view
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.25, self, "tick:", None, True
        )
        log("ui ready")

    def tick_(self, _t):
        cmd = read_json(CMD_FILE, {})
        ts = float(cmd.get("ts") or 0)
        if ts <= self.last_ts:
            self._maybe_expire()
            self._display_watchdog()
            return
        self.last_ts = ts
        action = cmd.get("action")
        log(f"ui cmd {action}")
        if action == "show":
            self.show_(cmd)
        elif action == "clear":
            self.clear_(None)
        elif action == "dismiss":
            self.dismiss_(None)
        elif action == "snapshot":
            self.snapshot_(cmd)
        elif action == "display":
            self.set_display(bool(cmd.get("on", True)), str(cmd.get("by") or "ctl"))

    # ---- display power: the shown page, or kiosk-ctl, decides; this process executes ----
    def userContentController_didReceiveScriptMessage_(self, _controller, message):
        raw = message.body()  # an NSDictionary or NSString, not a Python dict
        try:
            body = dict(raw)
        except (TypeError, ValueError):
            body = {"display": str(raw)}
        want = str(body.get("display", ""))
        if want not in ("on", "off"):
            log(f"bridge ignored {body!r}")
            return
        self.set_display(want == "on", "page", why=str(body.get("why", "")))

    def set_display(self, on: bool, by: str, why: str = ""):
        now = time.time()
        if on == self.display_on:
            if not on:
                self.display_asked_at = now  # the page renewed its request
            return
        self.display_on = on
        self.display_asked_at = now
        log(f"display {'on' if on else 'off'} by {by} {why}".rstrip())
        if on:
            wake_display()
        else:
            sleep_display()
        write_json(DISPLAY_FILE, {"on": on, "by": by, "why": why, "since": now})

    def _display_watchdog(self):
        if self.display_on:
            return
        if time.time() - self.display_asked_at > DISPLAY_OFF_RENEW_S:
            self.set_display(True, "watchdog", why="no renewal from the page")

    def _maybe_expire(self):
        state = read_json(STATE_FILE, {})
        until = state.get("until")
        if state.get("showing") and until and time.time() >= float(until):
            self.clear_(None)
            write_json(STATE_FILE, {"showing": False})

    def show_(self, cmd):
        self.set_display(True, "show")
        local = cmd.get("local")
        url = cmd.get("url")
        if local:
            file_url = NSURL.fileURLWithPath_(local)
            root = NSURL.fileURLWithPath_(str(Path(local).parent))
            self.webview.loadFileURL_allowingReadAccessToURL_(file_url, root)
        elif url:
            self.webview.loadRequest_(
                NSURLRequest.requestWithURL_(NSURL.URLWithString_(url))
            )
        screen = self.window.screen() or NSScreen.mainScreen()
        self.window.setFrame_display_(screen.frame(), True)
        self.window.setLevel_(SCREENSAVER_LEVEL)
        self.window.orderFrontRegardless()
        self.window.makeKeyAndOrderFront_(None)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        NSApplication.sharedApplication().setPresentationOptions_(
            NSApplicationPresentationHideDock | NSApplicationPresentationHideMenuBar
        )

    def clear_(self, _n):
        self.set_display(True, "clear")
        self.window.orderOut_(None)
        NSApplication.sharedApplication().setPresentationOptions_(0)
        self.webview.loadRequest_(
            NSURLRequest.requestWithURL_(NSURL.URLWithString_("about:blank"))
        )
        write_json(STATE_FILE, {"showing": False})

    def snapshot_(self, cmd):
        dest = cmd.get("path") or str(Path.home() / ".local/state/mac-kiosk-display/webview.png")

        def _done(image, err):
            if err is not None or image is None:
                log(f"snapshot err {err}")
                return
            from AppKit import NSBitmapImageRep, NSPNGFileType

            tiff = image.TIFFRepresentation()
            rep = NSBitmapImageRep.imageRepWithData_(tiff)
            data = rep.representationUsingType_properties_(NSPNGFileType, None)
            data.writeToFile_atomically_(dest, True)
            log(f"snapshot {dest}")

        self.webview.takeSnapshotWithConfiguration_completionHandler_(None, _done)

    def dismiss_(self, _n):
        for app in APPS:
            try:
                subprocess.run(
                    ["osascript", "-e", f'tell application "{app}" to quit'],
                    capture_output=True,
                    text=True,
                    timeout=6,
                )
            except Exception as exc:
                log(f"dismiss {app}: {exc}")
        subprocess.run(
            ["defaults", "write", "com.apple.dock", "autohide", "-bool", "false"],
            check=False,
        )
        subprocess.run(
            ["defaults", "delete", "com.apple.dock", "autohide-delay"],
            check=False,
            capture_output=True,
        )
        subprocess.run(["/usr/bin/killall", "Dock"], check=False, capture_output=True)
        log("dismiss done")


def main() -> None:
    from kiosk_lib import UI_PID_FILE

    UI_PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    UI_PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(0)
    delegate = KioskUI.alloc().init()
    app.setDelegate_(delegate)
    AppHelper.runEventLoop()


if __name__ == "__main__":
    main()

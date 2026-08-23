---
name: mac-kiosk-display
description: Fullscreen WebKit kiosk on a logged-in Mac.
version: 0.1.0
author: Daniel Schlaug, Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [macos, kiosk, display, kitchen]
    related_skills: []
---

# Mac kiosk display

Show a URL or local HTML file fullscreen on a **logged-in Mac GUI session**.
WebKit (WKWebView) fills the screen. Not wallpaper, Preview, or Safari chrome.

The kiosk process must run as a LaunchAgent in Aqua. SSH talks HTTP over a
**Unix socket** (`~/.local/state/mac-kiosk-display/kiosk.sock`) — not TCP —
so macOS never shows an “accept incoming connections” sheet.

## When to Use

- “Put this recipe / page / card on the kitchen Mac”
- “Keep the display on until tonight”
- Don’t use for: lock-screen bypass, typing passwords, or changing wallpaper

## Prerequisites

On the Mac (once), as the logged-in GUI user:

```bash
# from a clone of this skill / repo
bash scripts/install.sh
```

Needs Homebrew `python3` (or any 3.11+). Creates `~/.local/mac-kiosk-display/venv`
with PyObjC WebKit and a LaunchAgent `com.mac-kiosk-display`.

From another machine, SSH to that user must work (`BatchMode`). Do not put
hostnames or tokens in this file.

## How to Run

`terminal` on the Hermes hub (`MAC` is the SSH alias for the GUI Mac):

```bash
ssh "$MAC" 'kiosk-ctl show https://example.com --until tonight'
ssh "$MAC" 'kiosk-ctl show /Users/me/kiosk/card.html --until 23:59'
ssh "$MAC" 'kiosk-ctl dismiss'
ssh "$MAC" 'kiosk-ctl wake'
ssh "$MAC" 'kiosk-ctl snapshot'
ssh "$MAC" 'kiosk-ctl status'
ssh "$MAC" 'kiosk-ctl clear'
```

On the Mac itself, `kiosk-ctl` is on `PATH` after install (`~/bin/kiosk-ctl`).

## Procedure

1. Confirm the Mac GUI user is logged in (`ssh` + `launchctl print gui/$(id -u)`).
2. `kiosk-ctl status` — if connection refused, run `scripts/install.sh` on the Mac.
3. `kiosk-ctl dismiss` — quits Preview / Safari / System Settings from Aqua (SSH
   System Events hangs when Accessibility prompts are pending).
4. `kiosk-ctl wake` then `kiosk-ctl show <url|file> --until tonight`.
5. Verify with `kiosk-ctl snapshot` and copy that PNG back.
6. `kiosk-ctl clear` when done (also runs at `--until`).

## Pitfalls

- SSH `osascript` / System Events often **hangs** on pending Accessibility
  sheets. Dismiss from the LaunchAgent (`POST /dismiss`), not from SSH.
- No Xcode required. Broken CLT `xcrun` is fine; use Homebrew Python + PyObjC.
- Control is a Unix socket, not TCP. Optional `KIOSK_TOKEN` header.
- OS screencapture often misses the kiosk; use `kiosk-ctl snapshot`.
- Never set wallpaper as the display path. Never leave Dock hidden after `clear`.
- Do not signal processes whose names contain hermes or gateway.
- Display off: `POST /wake` (`caffeinate -u`). Hold-awake is `caffeinate -d` for
  the `--until` window.

## Verification

- `kiosk-ctl health` returns `{"ok": true, "service": "mac-kiosk-display"}`
- `kiosk-ctl snapshot` is the page, fullscreen, no Preview/Safari menu bar
- After `--until` or `clear`, desktop and Dock are back

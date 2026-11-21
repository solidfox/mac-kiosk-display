# mac-kiosk-display

Fullscreen **WebKit** kiosk for a logged-in Mac. A LaunchAgent owns a
borderless `WKWebView`. You show a URL or local HTML file with one command.
SSH never drives Safari, Preview, or wallpaper.

## Why

Remote `osascript` / System Events hangs when an Accessibility sheet is up.
Safari/Preview leave chrome. Wallpaper is the wrong layer. A TCP localhost
server can trigger macOS “accept incoming connections” sheets and then hang.

This process runs **in Aqua**. Control is HTTP over a **Unix socket**.

## Install (on the Mac, as the GUI user)

```bash
git clone https://github.com/solidfox/mac-kiosk-display.git
cd mac-kiosk-display
bash scripts/install.sh
```

Requires a working `python3` (Homebrew is fine; Xcode CLT is not required).

## Use

On the Mac:

```bash
kiosk-ctl show https://example.com --until tonight
kiosk-ctl show ~/Cards/recipe.html --until 22:30
kiosk-ctl dismiss    # quit leftover Preview/Safari/System Settings
kiosk-ctl snapshot   # PNG of the WKWebView
kiosk-ctl display off  # sleep the panel (the page keeps running); `on` wakes it
kiosk-ctl status
kiosk-ctl clear
```

From another machine:

```bash
ssh the-mac 'kiosk-ctl show https://example.com --until tonight'
```

`--until` accepts `tonight` (23:59 local), `HH:MM`, unix seconds, or a duration
in seconds. Display sleep is held with `caffeinate` until then.

## HTTP (Unix socket)

Socket: `~/.local/state/mac-kiosk-display/kiosk.sock`

```bash
curl --unix-socket "$HOME/.local/state/mac-kiosk-display/kiosk.sock" http://kiosk/health
```

| Method | Path | Body |
|--------|------|------|
| GET | `/health` | |
| GET | `/status` | |
| POST | `/show` | `{"url":"…","until":"tonight"}` |
| POST | `/clear` | `{}` |
| POST | `/wake` | `{}` |
| POST | `/dismiss` | `{}` |
| POST | `/snapshot` | `{"path":"optional.png"}` |
| POST | `/display` | `{"on":false}` sleeps the panel, `{"on":true}` wakes it |

## Display power

The kiosk holds `caffeinate -d -i`, so neither the panel nor the Mac idles to
sleep while a page is shown. A page may still ask for the panel to sleep (an LCD
showing black keeps its backlight lit): from JavaScript

```js
window.webkit.messageHandlers.kiosk.postMessage({ display: "off", why: "nobody here" });
window.webkit.messageHandlers.kiosk.postMessage({ display: "on" });
```

or from the shell, `kiosk-ctl display off|on`. A page that asked for "off" must
repeat it within 15 minutes or the panel wakes on its own, so a wedged page never
leaves the room dark. A new `show` or `clear` wakes it too. `kiosk-ctl status`
reports the last decision under `display`.

Optional `KIOSK_TOKEN` → `Authorization: Bearer …`.

OS `screencapture` often misses the kiosk window unless Screen Recording is
granted. Prefer `kiosk-ctl snapshot`.

## Hermes

This directory is a Hermes skill (`SKILL.md`).

```bash
hermes skills install github:solidfox/mac-kiosk-display --yes
```

## License

MIT

# Slink

Hide app buttons from the Windows taskbar — and the windows themselves.

![Version](https://img.shields.io/github/v/release/jaesungkr/slink?label=version)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-0078D6)
![License](https://img.shields.io/badge/License-MIT-green)

## Download

Grab the latest `Slink.exe` from [**Releases**](https://github.com/jaesungkr/slink/releases/latest).  
No installation needed — just run it.

## Features

- **Hide / Show** — Remove any window from the taskbar and screen, restore anytime
- **Background enforcer** — Re-hides windows that try to reappear (games, media players)
- **Search** — Filter the window list by process name or title
- **Dark / Light theme** — Toggle in Settings, persisted across sessions
- **System tray** — X button minimizes to tray, right-click to restore or quit
- **Auto-update** — Check and apply updates directly from the app
- **Single instance** — Mutex prevents duplicate launches

## How It Works

Slink modifies the window's extended style (`WS_EX_TOOLWINDOW`) and calls `ITaskbarList3.DeleteTab()` via COM to force-remove the taskbar button. A 1-second background watcher re-hides windows that try to reappear.

Hidden windows are removed from both the taskbar and the screen. All hidden windows are automatically restored on exit.

## Usage

1. Launch **Slink**
2. Select windows from the **Visible** list (use search to filter)
3. Click **Hide** — windows disappear from the taskbar and screen
4. Click **Show** to restore selected hidden windows
5. **X** button → minimizes to system tray
6. Tray icon → **Show** to reopen, **Quit** to exit

## Architecture

```
┌─────────────────────────────────────────────────┐
│  pywebview (frameless, WebView2/Edge Chromium)   │
│  ┌───────────────────────────────────────────┐   │
│  │  ui.html — HTML/CSS/JS dark & light UI    │   │
│  └────────────────┬──────────────────────────┘   │
│                   │ fetch()                      │
│  ┌────────────────▼──────────────────────────┐   │
│  │  HTTP API Server (127.0.0.1:18925)        │   │
│  │  gui.py — routes, settings, cmd queue     │   │
│  └────────────────┬──────────────────────────┘   │
│                   │                              │
│  ┌────────────────▼──────────────────────────┐   │
│  │  core.py + win32.py — WS_EX_TOOLWINDOW   │   │
│  │  + ITaskbarList3 COM + enforce loop       │   │
│  └───────────────────────────────────────────┘   │
│                                                  │
│  pystray (system tray) ◄─── cmd_queue ──► main   │
└─────────────────────────────────────────────────┘
```

No pywebview JS bridge is used (`js_api`, `expose`, `events` all avoided due to WinForms compatibility issues). All Python↔JS communication goes through the local HTTP server.

## Project Structure

```
main.py                — entry point, mutex, _MEI cleanup
ui.html                — single-file UI (HTML + CSS + JS)
slink/
  __init__.py          — app constants (version, author, repo)
  gui.py               — pywebview window + HTTP API server
  core.py              — hide / show / enforce logic
  win32.py             — Win32 API + ITaskbarList3 COM
  tray.py              — system tray (pystray)
  updater.py           — GitHub Releases auto-update
  resources.py         — resource path resolution
```

## Build from Source

```powershell
git clone https://github.com/jaesungkr/slink.git
cd slink
pip install -r requirements.txt
python main.py
```

### Build as .exe

Releases are built automatically via GitHub Actions on tag push.  
To build locally:

```powershell
pip install pyinstaller
pyinstaller --onefile --windowed --name Slink --icon=slink.ico ^
  --add-data "slink.ico;." --add-data "slink.png;." --add-data "ui.html;." ^
  --noconfirm main.py
```

Output: `dist/Slink.exe`

## Notes

- To hide apps running as Administrator, run Slink as Administrator too.
- Some UWP apps (Microsoft Store apps) may have limited support.
- Settings are stored in `%APPDATA%\Slink\settings.json`.

## Author

**ja2sng** — [github.com/jaesungkr](https://github.com/jaesungkr)

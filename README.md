# Slink

A lightweight Windows tool that hides app buttons from the taskbar — and the windows themselves.

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![Platform](https://img.shields.io/badge/Platform-Windows-0078D6)
![License](https://img.shields.io/badge/License-MIT-green)

## Download

Grab the latest `Slink.exe` from [Releases](https://github.com/jaesungkr/slink/releases/latest). No installation needed — just run it.

## How It Works

Slink modifies the window's extended style (`WS_EX_TOOLWINDOW`) and calls `ITaskbarList3.DeleteTab()` via COM to force-remove the taskbar button. A background watcher re-hides windows that try to reappear (common with games).

## Usage

1. **Launch** Slink — a splash screen appears while loading
2. In the **Main** tab, select a window from the list
3. Click **Hide** — the window disappears from the taskbar and screen
4. Click **Show** to restore it
5. **Closing** the window (X button) minimizes Slink to the system tray
6. **Right-click** the tray icon → Restore All & Quit to exit
7. All hidden windows are automatically restored on exit

## Settings

The **Settings** tab shows app info and has a one-click updater:

1. Click **Check for Updates**
2. If a new version is available, click **Update Now**
3. Slink downloads and replaces itself automatically

## Build from Source

```powershell
git clone https://github.com/jaesungkr/slink.git
cd slink
pip install -r requirements.txt
python slink.py
```

### Build as .exe

```powershell
pip install pyinstaller
pyinstaller Slink.spec
```

Output: `dist/Slink.exe`

## Project Structure

```
slink.py              — entry point + splash screen
slink/__init__.py     — app constants (version, author)
slink/win32.py        — Win32 API + ITaskbarList3 COM
slink/core.py         — hide / show / enforce logic
slink/gui.py          — Tkinter UI
slink/tray.py         — system tray
slink/updater.py      — GitHub Releases auto-update
slink/resources.py    — resource path resolution
```

## Notes

- To hide apps running as Administrator, run Slink as Administrator too.
- Duplicate launch is prevented via Windows Mutex.
- Some UWP apps (Microsoft Store apps) may have limited support.

## Author

**ja2sng** — [github.com/jaesungkr](https://github.com/jaesungkr)

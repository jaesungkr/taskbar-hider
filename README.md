# Slink

A lightweight Windows tool that hides app buttons from the taskbar — and the windows themselves.

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![Platform](https://img.shields.io/badge/Platform-Windows-0078D6)
![License](https://img.shields.io/badge/License-MIT-green)

## Download

Grab the latest `Slink.exe` from [Releases](https://github.com/jaesungkr/slink/releases/latest). No installation needed — just run it.

## How It Works

Slink modifies the window's extended style (`WS_EX_TOOLWINDOW`) and calls `ITaskbarList3.DeleteTab()` via COM to force-remove the taskbar button. A background watcher re-hides windows that try to reappear (common with games).

Hidden windows are fully hidden from both the taskbar and the screen. Use the app to restore them at any time.

## Usage

1. **Launch** Slink
2. In the **Windows** tab, select a window from the list
3. Click **Hide** — the window disappears from the taskbar and screen
4. Click **Show** to restore it
5. **Closing** the app (X button) minimizes Slink to the system tray
6. **Right-click** the tray icon → **Restore All & Quit** to exit
7. All hidden windows are automatically restored on exit

## Update

Slink has a built-in updater:

1. Go to the **Settings** tab
2. Click **Check for Updates**
3. If a new version is available, click **Update Now**
4. Slink downloads the update and closes automatically
5. A popup confirms when the update is complete
6. Reopen Slink — you're on the latest version

## Build from Source

```powershell
git clone https://github.com/jaesungkr/slink.git
cd slink
pip install -r requirements.txt
python main.py
```

### Build as .exe

```powershell
pip install pyinstaller
pyinstaller Slink.spec
```

Output: `dist/Slink.exe`

## Project Structure

```
main.py               — entry point + _MEI cleanup
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

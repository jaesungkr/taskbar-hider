# Slink

A lightweight tool to hide specific app buttons from the Windows taskbar while keeping them running in the background.

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![Platform](https://img.shields.io/badge/Platform-Windows-0078D6)
![License](https://img.shields.io/badge/License-MIT-green)

## How It Works

Slink modifies the [Extended Window Style](https://learn.microsoft.com/en-us/windows/win32/winmsg/extended-window-styles) of a target window and uses the `ITaskbarList3` COM interface to force-remove taskbar icons — even from apps (like games) that re-register them.

- Removes `WS_EX_APPWINDOW` + adds `WS_EX_TOOLWINDOW`
- Calls `ITaskbarList3.DeleteTab()` for stubborn apps
- Background watcher re-hides windows that reappear
- Hidden windows are fully hidden (not just removed from taskbar)

## Install

```powershell
git clone https://github.com/jaesungkr/slink.git
cd slink
pip install -r requirements.txt
python slink.py
```

Or download the latest `.exe` from [Releases](https://github.com/jaesungkr/slink/releases/latest).

## Usage

1. Launch Slink
2. **Main tab** — select a window → click **Hide** to hide it (window + taskbar button)
3. Click **Show** to restore a hidden window
4. Closing the window minimizes Slink to the system tray
5. Right-click tray icon → **Restore All & Quit** to exit

## Settings

The **Settings tab** shows app info, version, and has a one-click update checker that compares your version against the latest GitHub Release.

## Build as .exe

```powershell
pip install pyinstaller
pyinstaller --onefile --windowed --name Slink slink.py
```

Output: `dist/Slink.exe`

## Notes

- All hidden windows are automatically restored when Slink exits.
- To hide windows from apps running as Administrator, run Slink as Administrator too.
- Some UWP apps (Microsoft Store apps) may have limited support.

## Author

**ja2sng** — [github.com/jaesungkr](https://github.com/jaesungkr)

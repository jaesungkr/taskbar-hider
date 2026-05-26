# TaskbarHider

A lightweight tool to hide specific app buttons from the Windows taskbar while keeping them running in the background.

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![Platform](https://img.shields.io/badge/Platform-Windows-0078D6)
![License](https://img.shields.io/badge/License-MIT-green)

## How It Works

TaskbarHider modifies the [Extended Window Style](https://learn.microsoft.com/en-us/windows/win32/winmsg/extended-window-styles) of a target window:

- Removes `WS_EX_APPWINDOW` — disables taskbar visibility
- Adds `WS_EX_TOOLWINDOW` — excludes the window from the taskbar entirely

The application itself keeps running normally. You can still access hidden windows via `Alt+Tab` or by clicking on them directly.

## Quick Start

```powershell
git clone https://github.com/jaesungkr/taskbar-hider.git
cd taskbar-hider
python taskbar_hider.py
```

No external dependencies — uses only Python standard libraries (`ctypes`, `tkinter`).

## Usage

1. Launch the program — a GUI window opens
2. **Top list**: Windows currently visible on the taskbar
3. Select a window → click **Hide from Taskbar**
4. **Bottom list**: Windows hidden from the taskbar
5. Select a hidden window → click **Show on Taskbar** to restore it
6. **Restore All & Quit** — restores every hidden window and exits

## Build as .exe

```powershell
pip install pyinstaller
pyinstaller --onefile --windowed --name TaskbarHider taskbar_hider.py
```

The standalone executable will be generated at `dist/TaskbarHider.exe`.

## Notes

- All hidden windows are automatically restored when the program exits.
- To hide windows from apps running as Administrator, run TaskbarHider as Administrator too.
- Some UWP apps (Microsoft Store apps) may have limited support.

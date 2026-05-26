"""Slink — Hide app buttons from the Windows taskbar.

Usage:
    python slink.py
    or build with: pyinstaller Slink.spec
"""

import sys
import platform

if platform.system() != "Windows":
    print("Slink is Windows-only.")
    print("Run on Windows: python slink.py")
    print("Build:          pyinstaller Slink.spec")
    sys.exit(1)

from slink.core import SlinkCore
from slink.gui import SlinkGUI

if __name__ == "__main__":
    import ctypes
    # 단일 인스턴스 — Mutex로 중복 실행 방지
    mutex = ctypes.windll.kernel32.CreateMutexW(None, True, "Global\\SlinkAppMutex")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        ctypes.windll.user32.MessageBoxW(
            None, "Slink is already running.", "Slink", 0x40)
        sys.exit(0)

    core = SlinkCore()
    gui = SlinkGUI(core)
    gui.run()

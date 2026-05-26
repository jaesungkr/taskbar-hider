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


def show_splash():
    """로딩 중 스플래시 윈도우를 표시한다."""
    import tkinter as tk

    splash = tk.Tk()
    splash.overrideredirect(True)

    w, h = 280, 100
    sw = splash.winfo_screenwidth()
    sh = splash.winfo_screenheight()
    x = (sw - w) // 2
    y = (sh - h) // 2
    splash.geometry(f"{w}x{h}+{x}+{y}")

    splash.configure(bg="#fafaf8")
    splash.attributes("-topmost", True)

    tk.Label(splash, text="Slink", font=("Malgun Gothic", 16, "bold"),
             fg="#1a1a1a", bg="#fafaf8").pack(pady=(20, 2))
    tk.Label(splash, text="Loading...", font=("Malgun Gothic", 9),
             fg="#b0b0b0", bg="#fafaf8").pack()

    splash.update()
    return splash


if __name__ == "__main__":
    import ctypes

    # 단일 인스턴스 — Mutex로 중복 실행 방지
    mutex = ctypes.windll.kernel32.CreateMutexW(None, True, "Global\\SlinkAppMutex")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        ctypes.windll.user32.MessageBoxW(
            None, "Slink is already running.", "Slink", 0x40)
        sys.exit(0)

    # 스플래시 표시 → 무거운 import → 스플래시 닫기
    splash = show_splash()

    from slink.core import SlinkCore
    from slink.gui import SlinkGUI

    splash.destroy()

    core = SlinkCore()
    gui = SlinkGUI(core)
    gui.run()

"""Slink — Hide app buttons from the Windows taskbar.

Usage:
    python main.py
    or build with: pyinstaller Slink.spec
"""

import sys
import os
import platform

if platform.system() != "Windows":
    print("Slink is Windows-only.")
    print("Run on Windows: python main.py")
    print("Build:          pyinstaller Slink.spec")
    sys.exit(1)


def cleanup_old_mei():
    """이전 PyInstaller _MEI 임시 폴더를 정리한다.

    --onefile 모드에서 업데이트 후 재시작 시
    이전 프로세스의 _MEI 폴더가 남아있으면 DLL 충돌이 발생한다.
    현재 프로세스의 _MEI 폴더를 제외하고 나머지를 삭제한다.
    """
    if not getattr(sys, 'frozen', False):
        return

    import shutil
    import tempfile

    tmp = tempfile.gettempdir()
    # 현재 프로세스가 사용 중인 _MEI 폴더 (정규화)
    current_mei = os.path.normpath(getattr(sys, '_MEIPASS', ''))
    current_mei_name = os.path.basename(current_mei)

    try:
        for item in os.listdir(tmp):
            if not item.startswith('_MEI'):
                continue
            if not os.path.isdir(os.path.join(tmp, item)):
                continue
            # 현재 사용 중인 폴더는 절대 건드리지 않음
            if item == current_mei_name:
                continue
            try:
                shutil.rmtree(os.path.join(tmp, item))
            except PermissionError:
                # 다른 프로세스가 사용 중 — 정상, 무시
                pass
            except Exception:
                pass
    except Exception:
        pass


if __name__ == "__main__":
    # 이전 _MEI 잔여 폴더 정리 (DLL 충돌 방지)
    cleanup_old_mei()

    import ctypes

    # 단일 인스턴스 — Mutex로 중복 실행 방지
    mutex = ctypes.windll.kernel32.CreateMutexW(None, True, "Global\\SlinkAppMutex")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        ctypes.windll.user32.MessageBoxW(
            None, "Slink is already running.", "Slink", 0x40)
        sys.exit(0)

    # pywebview 내부 AccessibilityObject 재귀 에러 로그 억제
    import logging
    logging.getLogger('pywebview').setLevel(logging.CRITICAL)

    from slink.core import SlinkCore
    from slink.gui import SlinkGUI

    core = SlinkCore()
    gui = SlinkGUI(core)
    gui.run()

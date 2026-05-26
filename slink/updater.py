"""Auto-update via GitHub Releases API."""

import json
import os
import subprocess
import sys
import tempfile
import threading
import urllib.request

from slink import APP_NAME, APP_VERSION, APP_REPO


def check_for_update(callback):
    """백그라운드에서 최신 버전을 확인한다.

    callback(latest_version: str | None, download_url: str | None, error: str | None)
    """
    def _check():
        try:
            url = f"https://api.github.com/repos/{APP_REPO}/releases/latest"
            req = urllib.request.Request(url, headers={"User-Agent": APP_NAME})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())

            latest = data.get("tag_name", "").lstrip("v")
            if not latest:
                callback(None, None, "Could not determine latest version")
                return

            download_url = None
            for asset in data.get("assets", []):
                if asset["name"].lower().endswith(".exe"):
                    download_url = asset["browser_download_url"]
                    break

            if latest == APP_VERSION:
                callback(latest, None, None)
            else:
                callback(latest, download_url, None)

        except Exception as e:
            callback(None, None, str(e))

    threading.Thread(target=_check, daemon=True).start()


def download_and_apply(download_url: str, on_done, on_error):
    """최신 버전을 다운로드하고 교체한다."""
    def _download():
        try:
            is_frozen = getattr(sys, 'frozen', False)

            if is_frozen:
                app_exe = os.path.abspath(sys.executable)
                new_path = app_exe + ".new"
                old_path = app_exe + ".old"

                # 다운로드
                req = urllib.request.Request(
                    download_url, headers={"User-Agent": APP_NAME})
                with urllib.request.urlopen(req, timeout=120) as resp:
                    with open(new_path, "wb") as f:
                        while True:
                            chunk = resp.read(8192)
                            if not chunk:
                                break
                            f.write(chunk)

                # 배치 스크립트: PID 종료 대기 → 파일 교체 → 재시작
                bat_path = os.path.join(tempfile.gettempdir(), "slink_update.bat")
                pid = os.getpid()
                with open(bat_path, "w") as bat:
                    bat.write(f"""@echo off
:wait
tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul
if not errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto wait
)
timeout /t 1 /nobreak >nul
if exist "{old_path}" del /f "{old_path}"
move /y "{app_exe}" "{old_path}"
move /y "{new_path}" "{app_exe}"
start "" "{app_exe}"
timeout /t 3 /nobreak >nul
del /f "{old_path}"
del /f "%~f0"
""")

                def restart():
                    subprocess.Popen(["cmd", "/c", bat_path],
                                      creationflags=0x00000008)
                    sys.exit(0)

                on_done(restart)

            else:
                # .py 모드
                current_file = os.path.abspath(sys.argv[0])
                raw_url = f"https://raw.githubusercontent.com/{APP_REPO}/master/main.py"
                req = urllib.request.Request(
                    raw_url, headers={"User-Agent": APP_NAME})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    new_code = resp.read()

                with open(current_file, "wb") as f:
                    f.write(new_code)

                def restart():
                    subprocess.Popen([sys.executable] + sys.argv)
                    sys.exit(0)

                on_done(restart)

        except Exception as e:
            on_error(str(e))

    threading.Thread(target=_download, daemon=True).start()

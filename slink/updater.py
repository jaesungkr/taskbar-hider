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
    """최신 버전을 다운로드하고 교체한다.

    on_done(restart_func) — 메인 스레드에서 호출
    on_error(message: str) — 메인 스레드에서 호출
    """
    def _download():
        try:
            current_exe = os.path.abspath(sys.argv[0])
            is_frozen = getattr(sys, 'frozen', False)

            if is_frozen:
                new_path = current_exe + ".new"
                old_path = current_exe + ".old"

                req = urllib.request.Request(
                    download_url, headers={"User-Agent": APP_NAME})
                with urllib.request.urlopen(req, timeout=60) as resp:
                    with open(new_path, "wb") as f:
                        while True:
                            chunk = resp.read(8192)
                            if not chunk:
                                break
                            f.write(chunk)

                bat_path = os.path.join(tempfile.gettempdir(), "slink_update.bat")
                with open(bat_path, "w") as bat:
                    bat.write(f"""@echo off
ping 127.0.0.1 -n 3 > nul
if exist "{old_path}" del /f "{old_path}"
move /y "{current_exe}" "{old_path}"
move /y "{new_path}" "{current_exe}"
start "" "{current_exe}"
del /f "{old_path}"
del /f "%~f0"
""")

                def restart():
                    subprocess.Popen(["cmd", "/c", bat_path],
                                      creationflags=0x00000008)
                    sys.exit(0)

                on_done(restart)

            else:
                raw_url = f"https://raw.githubusercontent.com/{APP_REPO}/master/slink.py"
                req = urllib.request.Request(
                    raw_url, headers={"User-Agent": APP_NAME})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    new_code = resp.read()

                with open(current_exe, "wb") as f:
                    f.write(new_code)

                def restart():
                    subprocess.Popen([sys.executable] + sys.argv)
                    sys.exit(0)

                on_done(restart)

        except Exception as e:
            on_error(str(e))

    threading.Thread(target=_download, daemon=True).start()

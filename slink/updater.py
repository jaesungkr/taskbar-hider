"""Auto-update via GitHub Releases API."""

import json
import os
import subprocess
import sys
import tempfile
import threading
import urllib.request
import zipfile

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
                name = asset["name"].lower()
                if name.endswith(".zip") or name.endswith(".exe"):
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
                # .exe 모드 — zip 또는 exe 다운로드 후 폴더 교체
                app_dir = os.path.dirname(os.path.abspath(sys.executable))
                app_exe = os.path.abspath(sys.executable)
                tmp_dir = tempfile.mkdtemp(prefix="slink_update_")
                download_path = os.path.join(tmp_dir, "update_download")

                # 다운로드
                req = urllib.request.Request(
                    download_url, headers={"User-Agent": APP_NAME})
                with urllib.request.urlopen(req, timeout=120) as resp:
                    with open(download_path, "wb") as f:
                        while True:
                            chunk = resp.read(8192)
                            if not chunk:
                                break
                            f.write(chunk)

                # zip이면 풀기, exe면 그대로
                if download_url.lower().endswith(".zip"):
                    extract_dir = os.path.join(tmp_dir, "extracted")
                    with zipfile.ZipFile(download_path, 'r') as zf:
                        zf.extractall(extract_dir)
                    # zip 안에 Slink 폴더가 있을 수 있음
                    contents = os.listdir(extract_dir)
                    if len(contents) == 1 and os.path.isdir(
                            os.path.join(extract_dir, contents[0])):
                        source_dir = os.path.join(extract_dir, contents[0])
                    else:
                        source_dir = extract_dir
                else:
                    # 단일 exe
                    source_dir = None

                bat_path = os.path.join(tempfile.gettempdir(), "slink_update.bat")
                pid = os.getpid()

                if source_dir:
                    # 폴더 교체 방식
                    with open(bat_path, "w") as bat:
                        bat.write(f"""@echo off
echo Waiting for Slink to close...
:wait
tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul
if not errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto wait
)
timeout /t 1 /nobreak >nul
echo Updating files...
xcopy /s /y /q "{source_dir}\\*" "{app_dir}\\"
echo Starting Slink...
start "" "{app_exe}"
timeout /t 2 /nobreak >nul
rmdir /s /q "{tmp_dir}"
del /f "%~f0"
""")
                else:
                    # 단일 exe 교체
                    old_path = app_exe + ".old"
                    with open(bat_path, "w") as bat:
                        bat.write(f"""@echo off
echo Waiting for Slink to close...
:wait
tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul
if not errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto wait
)
timeout /t 1 /nobreak >nul
if exist "{old_path}" del /f "{old_path}"
move /y "{app_exe}" "{old_path}"
move /y "{download_path}" "{app_exe}"
start "" "{app_exe}"
timeout /t 2 /nobreak >nul
del /f "{old_path}"
rmdir /s /q "{tmp_dir}"
del /f "%~f0"
""")

                def restart():
                    subprocess.Popen(["cmd", "/c", bat_path],
                                      creationflags=0x00000008)
                    sys.exit(0)

                on_done(restart)

            else:
                # .py 모드 — main.py 교체
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

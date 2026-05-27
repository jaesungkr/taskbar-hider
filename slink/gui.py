"""Slink GUI — pywebview + HTML/CSS/JS for premium desktop UI."""

import os
import json
import threading

from slink import APP_NAME, APP_VERSION, APP_AUTHOR, APP_GITHUB
from slink.core import SlinkCore
from slink.win32 import enum_taskbar_windows
from slink.tray import setup_tray
from slink.updater import check_for_update, download_and_apply
from slink.resources import get_resource_path


class Api:
    """Python↔JS 브릿지. JS에서 pywebview.api.xxx()로 호출.

    주의: pywebview는 이 객체의 모든 public 속성/메서드를 재귀 탐색한다.
    - 모든 내부 상태는 _prefix (private)
    - pywebview Window 객체를 절대 public으로 노출하지 않을 것
    """

    def __init__(self, core: SlinkCore, window_ref, quit_callback=None):
        self._core = core
        self._window_ref = window_ref
        self._latest_download_url = None
        self._quit_callback = quit_callback

    def get_app_info(self):
        return {
            "name": APP_NAME,
            "version": APP_VERSION,
            "author": APP_AUTHOR,
            "github": APP_GITHUB,
        }

    def get_windows(self):
        """작업표시줄에 표시된 창 목록 반환."""
        try:
            import os
            own_pid = os.getpid()
            windows = enum_taskbar_windows()
            visible = []
            for w in windows:
                # 자기 자신 제외: PID 일치 or Slink.exe
                if w.get("pid") == own_pid:
                    continue
                proc = w["process"].lower()
                if proc.startswith("slink") and proc.endswith(".exe"):
                    continue
                visible.append({
                    "hwnd": w["hwnd"],
                    "title": w["title"],
                    "process": w["process"].replace(".exe", ""),
                })
            return {"visible": visible, "hidden": self._get_hidden()}
        except Exception as e:
            return {"visible": [], "hidden": [], "error": str(e)}

    def _get_hidden(self):
        return [
            {"hwnd": hwnd, "title": info.title,
             "process": info.process.replace(".exe", "")}
            for hwnd, info in self._core.hidden.items()
        ]

    def hide_windows(self, hwnds):
        """선택한 창들을 숨긴다."""
        count = 0
        for hwnd in hwnds:
            windows = enum_taskbar_windows()
            w = next((x for x in windows if x["hwnd"] == hwnd), None)
            if w and self._core.hide_from_taskbar(hwnd, w["title"], w["process"]):
                count += 1
        return {"hidden_count": count}

    def show_windows(self, hwnds):
        """숨긴 창들을 복원한다."""
        count = 0
        for hwnd in hwnds:
            if self._core.show_on_taskbar(hwnd):
                count += 1
        return {"shown_count": count}

    def check_update(self):
        """업데이트 확인 (동기)."""
        import queue
        q = queue.Queue()

        def cb(latest, url, err):
            q.put((latest, url, err))

        check_for_update(cb)
        latest, url, err = q.get(timeout=15)

        if err:
            return {"status": "error", "message": str(err)}
        elif url:
            self._latest_download_url = url
            return {"status": "available", "version": latest}
        else:
            return {"status": "up_to_date"}

    def do_update(self):
        """업데이트 다운로드 및 적용."""
        if not self._latest_download_url:
            return {"status": "error", "message": "No update URL"}

        import queue
        q = queue.Queue()

        def on_done(close_func):
            q.put(("done", close_func))

        def on_error(msg):
            q.put(("error", msg))

        download_and_apply(self._latest_download_url, on_done, on_error)
        result_type, payload = q.get(timeout=120)

        if result_type == "done":
            self._core.restore_all()
            payload()  # close_func — 프로세스 종료
            return {"status": "done"}
        else:
            return {"status": "error", "message": str(payload)}

    def open_releases(self):
        import webbrowser
        webbrowser.open(f"{APP_GITHUB}/releases/latest")

    def minimize_window(self):
        """창 최소화."""
        w = self._window_ref()
        if w:
            w.minimize()

    def hide_window(self):
        """창을 트레이로 숨김 (X 버튼)."""
        w = self._window_ref()
        if w:
            w.hide()

    def quit_app(self):
        """앱 종료."""
        if self._quit_callback:
            self._quit_callback()
        else:
            self._core.restore_all()
            w = self._window_ref()
            if w:
                w.destroy()


class SlinkGUI:
    def __init__(self, core: SlinkCore):
        self._core = core
        self.window = None
        self.tray_icon = None
        self._api = Api(core, lambda: self.window, quit_callback=self._on_quit)

    def _init_tray(self):
        png = get_resource_path("slink.png")
        self.tray_icon = setup_tray(
            on_show=lambda *_: self._restore_window(),
            on_quit=lambda *_: self._on_quit(),
            icon_path=png)

    def _restore_window(self):
        if self.window:
            self.window.show()
            self.window.restore()

    def _on_quit(self):
        self._core.restore_all()
        if self.tray_icon:
            self.tray_icon.stop()
        if self.window:
            self.window.destroy()

    def _start_enforce_loop(self):
        """1초마다 숨김 상태 유지."""
        def loop():
            import time
            while True:
                try:
                    if self._core.hidden:
                        self._core.enforce_hidden()
                except Exception:
                    pass
                time.sleep(1)

        t = threading.Thread(target=loop, daemon=True)
        t.start()

    def run(self):
        import webview

        html_path = get_resource_path("ui.html")

        # 파일이 없으면 대체 경로 시도
        if not os.path.exists(html_path):
            for alt in [
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ui.html"),
                os.path.join(os.getcwd(), "ui.html"),
            ]:
                alt = os.path.normpath(alt)
                if os.path.exists(alt):
                    html_path = alt
                    break

        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        self.window = webview.create_window(
            "Slink",
            html=html_content,
            width=540,
            height=520,
            min_size=(420, 380),
            frameless=True,
            easy_drag=False,
            background_color="#171717",
        )

        def on_start():
            self._init_tray()
            self._start_enforce_loop()

            # expose로 개별 함수 노출 (js_api 객체 탐색 회피)
            # 바운드 메서드를 래핑 — expose는 __name__ 속성이 필요
            api = self._api

            def get_app_info(): return api.get_app_info()
            def get_windows(): return api.get_windows()
            def hide_windows(hwnds): return api.hide_windows(hwnds)
            def show_windows(hwnds): return api.show_windows(hwnds)
            def check_update(): return api.check_update()
            def do_update(): return api.do_update()
            def open_releases(): return api.open_releases()
            def minimize_window(): return api.minimize_window()
            def hide_window(): return api.hide_window()
            def quit_app(): return api.quit_app()

            self.window.expose(
                get_app_info, get_windows, hide_windows, show_windows,
                check_update, do_update, open_releases,
                minimize_window, hide_window, quit_app,
            )

        ico = get_resource_path("slink.ico")

        webview.start(func=on_start, debug=False, gui="edgechromium",
                      icon=ico if os.path.exists(ico) else None)

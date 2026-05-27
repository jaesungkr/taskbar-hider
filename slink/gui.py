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
    """Python↔JS 브릿지. JS에서 pywebview.api.xxx()로 호출."""

    def __init__(self, core: SlinkCore, window_ref, quit_callback=None):
        self._core = core
        self._window_ref = window_ref  # lambda로 지연 참조
        self._latest_download_url = None
        self._quit_callback = quit_callback

    @property
    def window(self):
        return self._window_ref()

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
            windows = enum_taskbar_windows()
            # pywebview 자신의 창은 제외
            visible = []
            for w in windows:
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
        if self.window:
            self.window.minimize()

    def hide_window(self):
        """창을 트레이로 숨김 (X 버튼)."""
        if self.window:
            self.window.hide()

    def quit_app(self):
        """앱 종료."""
        if self._quit_callback:
            self._quit_callback()
        else:
            self._core.restore_all()
            if self.window:
                self.window.destroy()


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

    def _on_closing(self):
        """OS X 버튼 → 트레이로 숨김."""
        if self.window:
            self.window.hide()
        return False  # True=닫기 허용, False=닫기 차단

    def _hook_close_button(self):
        """Win32 WndProc 서브클래싱으로 X 버튼을 트레이 숨김으로 변경.

        pywebview closing 이벤트가 AccessibilityObject 재귀를 유발하므로
        직접 Win32 API로 WM_CLOSE를 가로챈다.
        """
        import ctypes
        import ctypes.wintypes as wintypes

        user32 = ctypes.windll.user32
        GWL_WNDPROC = -4
        WM_CLOSE = 0x0010

        WNDPROC = ctypes.WINFUNCTYPE(
            ctypes.c_long, wintypes.HWND, ctypes.c_uint,
            wintypes.WPARAM, wintypes.LPARAM
        )

        # Slink 창의 hwnd 찾기
        hwnd = None
        def enum_cb(h, _):
            nonlocal hwnd
            length = user32.GetWindowTextLengthW(h)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(h, buf, length + 1)
                if buf.value == "Slink":
                    pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
                    import os
                    if pid.value == os.getpid():
                        hwnd = h
                        return False
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)

        if not hwnd:
            return

        # 원래 WndProc 저장
        old_proc = user32.GetWindowLongPtrW(hwnd, GWL_WNDPROC)

        def new_proc(h, msg, wp, lp):
            if msg == WM_CLOSE:
                # X 버튼 → 트레이로 숨김
                if self.window:
                    self.window.hide()
                return 0  # 닫기 차단
            return user32.CallWindowProcW(old_proc, h, msg, wp, lp)

        self._wndproc_ref = WNDPROC(new_proc)  # prevent GC
        user32.SetWindowLongPtrW(hwnd, GWL_WNDPROC,
                                  ctypes.cast(self._wndproc_ref, ctypes.c_void_p).value)

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

        # HTML을 문자열로 읽어서 직접 로드 (경로 문제 회피)
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        self.window = webview.create_window(
            "Slink",
            html=html_content,
            js_api=self._api,
            width=540,
            height=520,
            min_size=(420, 380),
            frameless=False,
            easy_drag=False,
            background_color="#171717",
        )

        def on_start():
            self._init_tray()
            self._start_enforce_loop()
            # Win32 서브클래싱으로 X 버튼 → 트레이 숨김
            import time
            time.sleep(0.5)  # 창 생성 완료 대기
            try:
                self._hook_close_button()
            except Exception:
                pass

        # 아이콘 설정
        ico = get_resource_path("slink.ico")

        webview.start(func=on_start, debug=False, gui="edgechromium",
                      icon=ico if os.path.exists(ico) else None)

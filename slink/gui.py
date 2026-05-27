"""Slink GUI — pywebview + local HTTP API server.

검증된 패턴:
- webview.start(func, window) 형태로 window를 인자로 받기
- window.hide()/show()는 start func에서 받은 window 객체로 직접 호출
- pystray는 별도 스레드에서 실행, 콜백에서 window.show() 직접 호출
- HTTP 서버는 별도 스레드, 창 제어는 cmd_queue 경유
"""

import os
import json
import queue
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

from slink import APP_NAME, APP_VERSION, APP_AUTHOR, APP_GITHUB
from slink.core import SlinkCore
from slink.win32 import enum_taskbar_windows
from slink.tray import setup_tray
from slink.updater import check_for_update, download_and_apply
from slink.resources import get_resource_path

# 전역 참조 — HTTP 핸들러와 트레이에서 접근
_window = None
_core = None
_tray = None
_cmd_queue = queue.Queue()


class ApiHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/info":
            self._json({"name": APP_NAME, "version": APP_VERSION,
                         "author": APP_AUTHOR, "github": APP_GITHUB})
        elif self.path == "/api/windows":
            self._json(self._get_windows())
        elif self.path == "/api/check_update":
            self._json(self._check_update())
        elif self.path == "/api/open_releases":
            import webbrowser
            webbrowser.open(f"{APP_GITHUB}/releases/latest")
            self._json({"ok": True})
        elif self.path in ("/api/minimize", "/api/hide", "/api/quit"):
            cmd = self.path.split("/")[-1]
            self._json({"ok": True})
            _cmd_queue.put(cmd)
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        body = self._body()
        if self.path == "/api/hide_windows":
            count = 0
            for hwnd in body.get("hwnds", []):
                ws = enum_taskbar_windows()
                w = next((x for x in ws if x["hwnd"] == hwnd), None)
                if w and _core.hide_from_taskbar(hwnd, w["title"], w["process"]):
                    count += 1
            self._json({"hidden_count": count})
        elif self.path == "/api/show_windows":
            count = 0
            for hwnd in body.get("hwnds", []):
                if _core.show_on_taskbar(hwnd):
                    count += 1
            self._json({"shown_count": count})
        elif self.path == "/api/do_update":
            self._json(self._do_update())
        else:
            self._json({"error": "not found"}, 404)

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(n)) if n else {}
        except Exception:
            return {}

    def _json(self, d, code=200):
        b = json.dumps(d).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _get_windows(self):
        pid = os.getpid()
        visible = []
        for w in enum_taskbar_windows():
            if w.get("pid") == pid:
                continue
            p = w["process"].lower()
            if p.startswith("slink") and p.endswith(".exe"):
                continue
            visible.append({"hwnd": w["hwnd"], "title": w["title"],
                            "process": w["process"].replace(".exe", "")})
        hidden = [{"hwnd": h, "title": i.title,
                    "process": i.process.replace(".exe", "")}
                   for h, i in _core.hidden.items()]
        return {"visible": visible, "hidden": hidden}

    def _check_update(self):
        q = queue.Queue()
        check_for_update(lambda l, u, e: q.put((l, u, e)))
        try:
            l, u, e = q.get(timeout=15)
        except Exception:
            return {"status": "error", "message": "timeout"}
        if e:
            return {"status": "error", "message": str(e)}
        if u:
            ApiHandler._update_url = u
            return {"status": "available", "version": l}
        return {"status": "up_to_date"}

    def _do_update(self):
        u = getattr(ApiHandler, "_update_url", None)
        if not u:
            return {"status": "error", "message": "No URL"}

        def on_done(close_func):
            _core.restore_all()
            close_func()

        def on_error(msg):
            pass  # UI에서 타임아웃으로 처리

        download_and_apply(u, on_done, on_error)
        return {"status": "downloading"}


def _do_quit():
    global _window, _tray
    _core.restore_all()
    if _tray:
        try:
            _tray.stop()
        except Exception:
            pass
    if _window:
        _window.destroy()


def _main_loop(window):
    """webview.start에서 호출되는 메인 함수.

    이 함수가 실행되는 스레드에서 window.hide()/show() 호출이 검증됨.
    """
    global _window, _tray
    _window = window

    # 트레이 설정
    png = get_resource_path("slink.png")
    _tray = setup_tray(
        on_show=lambda *_: _cmd_queue.put("show"),
        on_quit=lambda *_: _cmd_queue.put("quit"),
        icon_path=png)

    print("[Slink] Tray icon:", "OK" if _tray else "FAILED")

    # enforce 루프
    def enforce():
        import time
        while True:
            try:
                if _core.hidden:
                    _core.enforce_hidden()
            except Exception:
                pass
            time.sleep(1)
    threading.Thread(target=enforce, daemon=True).start()

    # 명령 큐 처리 — 이 스레드에서 실행 (검증된 패턴)
    import time
    while True:
        try:
            cmd = _cmd_queue.get(timeout=0.3)
        except queue.Empty:
            continue


        if cmd == "hide":
            window.hide()
        elif cmd == "show":
            window.show()
            window.restore()
        elif cmd == "minimize":
            window.minimize()
        elif cmd == "quit":
            _do_quit()
            break


class SlinkGUI:
    def __init__(self, core: SlinkCore):
        global _core
        _core = core

    def run(self):
        import webview

        # HTTP API 서버
        port = 18925
        server = HTTPServer(("127.0.0.1", port), ApiHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()

        # HTML 로드
        html_path = get_resource_path("ui.html")
        if not os.path.exists(html_path):
            for alt in [
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ui.html"),
                os.path.join(os.getcwd(), "ui.html"),
            ]:
                if os.path.exists(os.path.normpath(alt)):
                    html_path = os.path.normpath(alt)
                    break

        with open(html_path, "r", encoding="utf-8") as f:
            html = f.read().replace("__API_PORT__", str(port))

        w = webview.create_window(
            "Slink", html=html,
            width=540, height=520, min_size=(420, 380),
            frameless=True, easy_drag=False,
            background_color="#171717",
        )

        ico = get_resource_path("slink.ico")
        webview.start(_main_loop, w, debug=False, gui="edgechromium",
                      icon=ico if os.path.exists(ico) else None)

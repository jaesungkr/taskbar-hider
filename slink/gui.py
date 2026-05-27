"""Slink GUI — pywebview + local HTTP API server.

Architecture:
- pywebview: 창 렌더링 전용 (js_api/expose/events 일절 사용 안 함)
- HTTP server (127.0.0.1:PORT): JS↔Python 통신
- 창 제어 (hide/minimize/quit): 큐를 통해 메인 루프에서 실행
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

# 창 제어 명령 큐 — HTTP 스레드 → 메인 루프
_cmd_queue = queue.Queue()


class ApiHandler(BaseHTTPRequestHandler):
    """로컬 HTTP API."""

    core: SlinkCore = None
    gui_ref = None

    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/api/info":
            self._json({"name": APP_NAME, "version": APP_VERSION,
                         "author": APP_AUTHOR, "github": APP_GITHUB})

        elif self.path == "/api/windows":
            self._json(self._get_all_windows())

        elif self.path == "/api/check_update":
            self._json(self._check_update())

        elif self.path == "/api/open_releases":
            import webbrowser
            webbrowser.open(f"{APP_GITHUB}/releases/latest")
            self._json({"ok": True})

        elif self.path == "/api/minimize":
            self._json({"ok": True})
            _cmd_queue.put("minimize")

        elif self.path == "/api/hide":
            self._json({"ok": True})
            _cmd_queue.put("hide")

        elif self.path == "/api/quit":
            self._json({"ok": True})
            _cmd_queue.put("quit")

        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        body = self._read_body()

        if self.path == "/api/hide_windows":
            hwnds = body.get("hwnds", [])
            count = 0
            for hwnd in hwnds:
                windows = enum_taskbar_windows()
                w = next((x for x in windows if x["hwnd"] == hwnd), None)
                if w and ApiHandler.core.hide_from_taskbar(hwnd, w["title"], w["process"]):
                    count += 1
            self._json({"hidden_count": count})

        elif self.path == "/api/show_windows":
            hwnds = body.get("hwnds", [])
            count = 0
            for hwnd in hwnds:
                if ApiHandler.core.show_on_taskbar(hwnd):
                    count += 1
            self._json({"shown_count": count})

        elif self.path == "/api/do_update":
            self._json(self._do_update())

        else:
            self._json({"error": "not found"}, 404)

    def _read_body(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = self.rfile.read(length)
            return json.loads(data) if data else {}
        except Exception:
            return {}

    def _json(self, data, code=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _get_all_windows(self):
        own_pid = os.getpid()
        windows = enum_taskbar_windows()
        visible = []
        for w in windows:
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

        hidden = [
            {"hwnd": hwnd, "title": info.title,
             "process": info.process.replace(".exe", "")}
            for hwnd, info in ApiHandler.core.hidden.items()
        ]
        return {"visible": visible, "hidden": hidden}

    def _check_update(self):
        q = queue.Queue()
        check_for_update(lambda latest, url, err: q.put((latest, url, err)))
        try:
            latest, url, err = q.get(timeout=15)
        except Exception:
            return {"status": "error", "message": "timeout"}
        if err:
            return {"status": "error", "message": str(err)}
        elif url:
            ApiHandler._update_url = url
            return {"status": "available", "version": latest}
        return {"status": "up_to_date"}

    def _do_update(self):
        url = getattr(ApiHandler, "_update_url", None)
        if not url:
            return {"status": "error", "message": "No update URL"}
        q = queue.Queue()
        download_and_apply(url,
                           lambda close_func: q.put(("done", close_func)),
                           lambda msg: q.put(("error", msg)))
        try:
            result_type, payload = q.get(timeout=120)
        except Exception:
            return {"status": "error", "message": "timeout"}
        if result_type == "done":
            ApiHandler.core.restore_all()
            payload()
            return {"status": "done"}
        return {"status": "error", "message": str(payload)}


def _start_api_server(core, gui, port=18925):
    ApiHandler.core = core
    ApiHandler.gui_ref = gui
    server = HTTPServer(("127.0.0.1", port), ApiHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return port


class SlinkGUI:
    def __init__(self, core: SlinkCore):
        self._core = core
        self.window = None
        self.tray_icon = None

    def _init_tray(self):
        png = get_resource_path("slink.png")
        self.tray_icon = setup_tray(
            on_show=lambda *_: _cmd_queue.put("show"),
            on_quit=lambda *_: _cmd_queue.put("quit"),
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
        def loop():
            import time
            while True:
                try:
                    if self._core.hidden:
                        self._core.enforce_hidden()
                except Exception:
                    pass
                time.sleep(1)
        threading.Thread(target=loop, daemon=True).start()

    def _start_cmd_loop(self):
        """큐에서 명령을 꺼내 메인 스레드(evaluate_js)로 실행.

        pywebview의 window.hide/show/minimize는
        WinForms Invoke가 필요하므로 아무 스레드에서나 호출 가능하지만,
        frameless 모드에서 타이밍 이슈가 있으므로
        evaluate_js를 통해 간접 실행한다.
        """
        def loop():
            import time
            while True:
                try:
                    cmd = _cmd_queue.get(timeout=0.2)
                except queue.Empty:
                    continue

                try:
                    if cmd == "hide":
                        if self.window:
                            self.window.hide()
                    elif cmd == "show":
                        if self.window:
                            self.window.show()
                            self.window.restore()
                    elif cmd == "minimize":
                        if self.window:
                            self.window.minimize()
                    elif cmd == "quit":
                        self._on_quit()
                        break
                except Exception:
                    pass

        threading.Thread(target=loop, daemon=True).start()

    def run(self):
        import webview

        # 1) HTTP API 서버
        port = _start_api_server(self._core, self)

        # 2) HTML 로드
        html_path = get_resource_path("ui.html")
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
        html_content = html_content.replace("__API_PORT__", str(port))

        # 3) pywebview 창 — js_api 없음, events 없음
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
            self._start_cmd_loop()

        ico = get_resource_path("slink.ico")
        webview.start(func=on_start, debug=False, gui="edgechromium",
                      icon=ico if os.path.exists(ico) else None)

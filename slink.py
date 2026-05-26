"""
Slink - Windows 작업표시줄에서 특정 앱 버튼을 숨기는 도구

원리:
  1차: 창의 확장 스타일(WS_EX_TOOLWINDOW)을 변경하여 작업표시줄에서 제거
  2차: ITaskbarList3 COM 인터페이스로 명시적으로 탭을 삭제
  일부 앱(게임 등)은 COM을 통해 직접 아이콘을 등록하므로 두 방법을 병행한다.

사용법:
  1. python slink.py 실행
  2. GUI 창에서 숨기고 싶은 앱 선택 → Hide 버튼 클릭
  3. 다시 보이게 하려면 → Show 버튼 클릭

요구사항:
  pip install comtypes
"""

import ctypes
import ctypes.wintypes as wintypes
import threading
import tkinter as tk
from tkinter import ttk
from dataclasses import dataclass, field
from typing import Dict, Optional
import webbrowser
import urllib.request
import json

# ──────────────────────────────────────────────
# 앱 정보
# ──────────────────────────────────────────────
APP_NAME = "Slink"
APP_VERSION = "1.0.0"
APP_AUTHOR = "ja2sng"
APP_REPO = "jaesungkr/slink"
APP_GITHUB = f"https://github.com/{APP_REPO}"

# ──────────────────────────────────────────────
# Win32 API 상수 및 함수
# ──────────────────────────────────────────────
user32 = ctypes.windll.user32
ole32 = ctypes.windll.ole32

GWL_EXSTYLE = -20
WS_EX_APPWINDOW = 0x00040000
WS_EX_TOOLWINDOW = 0x00000080

SW_HIDE = 0
SW_SHOW = 5
SW_SHOWNOACTIVATE = 4

# SetWindowPos 상수
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
SWP_NOZORDER = 0x0004

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


# ──────────────────────────────────────────────
# ITaskbarList3 COM 인터페이스 (직접 정의)
# ──────────────────────────────────────────────
import comtypes
import comtypes.client
from comtypes import GUID, HRESULT, COMMETHOD
from ctypes import POINTER

class ITaskbarList(comtypes.IUnknown):
    _iid_ = GUID("{56FDF342-FD6D-11d0-958A-006097C9A090}")
    _methods_ = [
        COMMETHOD([], HRESULT, "HrInit"),
        COMMETHOD([], HRESULT, "AddTab", (["in"], wintypes.HWND, "hwnd")),
        COMMETHOD([], HRESULT, "DeleteTab", (["in"], wintypes.HWND, "hwnd")),
        COMMETHOD([], HRESULT, "ActivateTab", (["in"], wintypes.HWND, "hwnd")),
        COMMETHOD([], HRESULT, "SetActiveAlt", (["in"], wintypes.HWND, "hwnd")),
    ]

class ITaskbarList2(ITaskbarList):
    _iid_ = GUID("{602D4995-B13A-429b-A66E-1935E44F4317}")
    _methods_ = [
        COMMETHOD([], HRESULT, "MarkFullscreenWindow",
                  (["in"], wintypes.HWND, "hwnd"),
                  (["in"], wintypes.BOOL, "fFullscreen")),
    ]

# TBPFLAG enum values
TBPF_NOPROGRESS = 0x00000000

class ITaskbarList3(ITaskbarList2):
    _iid_ = GUID("{ea1afb91-9e28-4b86-90e9-9e9f8a5eefaf}")
    _methods_ = [
        COMMETHOD([], HRESULT, "SetProgressValue",
                  (["in"], wintypes.HWND, "hwnd"),
                  (["in"], ctypes.c_ulonglong, "ullCompleted"),
                  (["in"], ctypes.c_ulonglong, "ullTotal")),
        COMMETHOD([], HRESULT, "SetProgressState",
                  (["in"], wintypes.HWND, "hwnd"),
                  (["in"], ctypes.c_int, "tbpFlags")),
    ]

CLSID_TaskbarList = GUID("{56FDF344-FD6D-11d0-958A-006097C9A090}")


def create_taskbar_list() -> ITaskbarList3:
    """ITaskbarList3 COM 객체를 생성한다."""
    ole32.CoInitialize(None)
    taskbar = comtypes.CoCreateInstance(
        CLSID_TaskbarList, interface=ITaskbarList3
    )
    taskbar.HrInit()
    return taskbar


def get_window_text(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def get_window_exstyle(hwnd: int) -> int:
    return user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)


def set_window_exstyle(hwnd: int, style: int):
    user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style)


def is_window_visible(hwnd: int) -> bool:
    return bool(user32.IsWindowVisible(hwnd))


def get_window_pid(hwnd: int) -> int:
    """창 핸들로부터 PID를 가져온다."""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def get_process_name(hwnd: int) -> str:
    """창 핸들로부터 프로세스 이름을 가져온다."""
    pid = get_window_pid(hwnd)

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32 = ctypes.windll.kernel32
    h_process = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h_process:
        return "unknown"

    try:
        buf = ctypes.create_unicode_buffer(260)
        size = wintypes.DWORD(260)
        kernel32.QueryFullProcessImageNameW(h_process, 0, buf, ctypes.byref(size))
        full_path = buf.value
        return full_path.rsplit("\\", 1)[-1] if full_path else "unknown"
    finally:
        kernel32.CloseHandle(h_process)


def find_all_windows_by_pid(target_pid: int) -> list:
    """특정 PID에 속하는 모든 최상위 창을 반환한다."""
    results = []

    def callback(hwnd, _lparam):
        pid = get_window_pid(hwnd)
        if pid == target_pid and is_window_visible(hwnd):
            results.append(hwnd)
        return True

    user32.EnumWindows(WNDENUMPROC(callback), 0)
    return results


def enum_taskbar_windows() -> list:
    """작업표시줄에 표시되는 창 목록을 반환한다."""
    results = []

    def callback(hwnd, _lparam):
        if not is_window_visible(hwnd):
            return True
        title = get_window_text(hwnd)
        if not title:
            return True

        ex_style = get_window_exstyle(hwnd)

        # 작업표시줄에 표시되는 조건:
        # - WS_EX_TOOLWINDOW가 아니거나
        # - WS_EX_APPWINDOW가 설정된 경우
        is_toolwindow = bool(ex_style & WS_EX_TOOLWINDOW)
        is_appwindow = bool(ex_style & WS_EX_APPWINDOW)

        # owner가 없고 TOOLWINDOW가 아닌 창, 또는 APPWINDOW인 창
        owner = user32.GetWindow(hwnd, 4)  # GW_OWNER = 4
        if (not owner and not is_toolwindow) or is_appwindow:
            process_name = get_process_name(hwnd)
            results.append({
                "hwnd": hwnd,
                "title": title,
                "process": process_name,
                "ex_style": ex_style,
            })
        return True

    user32.EnumWindows(WNDENUMPROC(callback), 0)
    return results


# ──────────────────────────────────────────────
# 핵심 로직: 숨기기 / 보이기
# ──────────────────────────────────────────────
@dataclass
class HiddenWindow:
    hwnd: int
    title: str
    process: str
    original_exstyle: int


class SlinkCore:
    def __init__(self):
        self.hidden: Dict[int, HiddenWindow] = {}
        try:
            self.taskbar_list = create_taskbar_list()
        except Exception:
            self.taskbar_list = None

    def hide_from_taskbar(self, hwnd: int, title: str, process: str) -> bool:
        """작업표시줄에서 창 버튼을 숨기고 창도 최소화한다."""
        if hwnd in self.hidden:
            return False

        # 같은 프로세스의 모든 창을 찾아서 함께 숨김
        target_pid = get_window_pid(hwnd)
        sibling_hwnds = find_all_windows_by_pid(target_pid)

        for h in sibling_hwnds:
            if h in self.hidden:
                continue

            original_style = get_window_exstyle(h)
            h_title = get_window_text(h) or f"(child of {process})"

            # 스타일 변경
            user32.ShowWindow(h, SW_HIDE)
            new_style = (original_style & ~WS_EX_APPWINDOW) | WS_EX_TOOLWINDOW
            set_window_exstyle(h, new_style)

            # 창을 숨긴 상태로 유지 (최소화)
            user32.ShowWindow(h, SW_HIDE)

            # COM으로 명시적 제거
            if self.taskbar_list:
                try:
                    self.taskbar_list.DeleteTab(h)
                except Exception:
                    pass

            self.hidden[h] = HiddenWindow(
                hwnd=h,
                title=h_title,
                process=process,
                original_exstyle=original_style,
            )

        return True

    def show_on_taskbar(self, hwnd: int) -> bool:
        """숨겨진 창을 복원하고 작업표시줄에 다시 표시한다."""
        if hwnd not in self.hidden:
            return False

        info = self.hidden[hwnd]

        # 스타일 복원 후 창 다시 표시
        set_window_exstyle(hwnd, info.original_exstyle)
        user32.ShowWindow(hwnd, SW_SHOW)

        # COM으로 다시 등록
        if self.taskbar_list:
            try:
                self.taskbar_list.AddTab(hwnd)
            except Exception:
                pass

        del self.hidden[hwnd]
        return True

    def enforce_hidden(self):
        """숨긴 창이 다시 작업표시줄에 나타났으면 다시 숨긴다."""
        for hwnd, info in list(self.hidden.items()):
            # 창이 아직 존재하는지 확인
            if not user32.IsWindow(hwnd):
                del self.hidden[hwnd]
                continue

            # 스타일이 원래대로 돌아갔는지 확인
            current_style = get_window_exstyle(hwnd)
            has_toolwindow = bool(current_style & WS_EX_TOOLWINDOW)

            if not has_toolwindow:
                # 앱이 스타일을 되돌린 경우 → 다시 적용하고 숨김
                new_style = (current_style & ~WS_EX_APPWINDOW) | WS_EX_TOOLWINDOW
                set_window_exstyle(hwnd, new_style)
                user32.ShowWindow(hwnd, SW_HIDE)

            # 창이 다시 보이게 된 경우 → 다시 숨김
            if is_window_visible(hwnd):
                user32.ShowWindow(hwnd, SW_HIDE)

            # COM으로도 다시 제거
            if self.taskbar_list:
                try:
                    self.taskbar_list.DeleteTab(hwnd)
                except Exception:
                    pass

    def restore_all(self):
        """모든 숨긴 창을 복원한다. (종료 시 호출)"""
        for hwnd in list(self.hidden.keys()):
            self.show_on_taskbar(hwnd)


# ──────────────────────────────────────────────
# GUI (Tkinter)
# ──────────────────────────────────────────────
class SlinkGUI:
    def __init__(self, core: SlinkCore):
        self.core = core
        self.tray_icon = None
        self.root = tk.Tk()
        self.root.title("Slink")
        self.root.geometry("720x700")
        self.root.configure(bg="#fafaf8")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._apply_style()
        self._build_ui()
        self._refresh_list()
        self._start_watcher()
        self._setup_tray()

    def _apply_style(self):
        style = ttk.Style()
        style.theme_use("clam")

        FONT = "Malgun Gothic"
        BG = "#fafaf8"
        FG = "#222222"
        FG_DIM = "#999999"
        SURFACE = "#f0efed"
        HOVER = "#e6e5e3"
        SELECT = "#dddcda"
        HEAD_BG = "#333333"
        HEAD_FG = "#f0efed"

        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=FG,
                         font=(FONT, 10))
        style.configure("Title.TLabel", font=(FONT, 16, "bold"),
                         foreground="#111111", background=BG)
        style.configure("Section.TLabel", font=(FONT, 9),
                         foreground=FG_DIM, background=BG)

        # 기본 버튼
        style.configure("TButton", font=(FONT, 10), padding=(12, 6),
                         background=SURFACE, foreground=FG,
                         borderwidth=1, relief="solid")
        style.map("TButton",
                   background=[("active", HOVER)])

        # Hide 버튼
        style.configure("Hide.TButton", font=(FONT, 10, "bold"),
                         padding=(14, 7), background="#333333",
                         foreground="#f0efed", borderwidth=0)
        style.map("Hide.TButton",
                   background=[("active", "#444444")],
                   foreground=[("active", "#f0efed")])

        # Show 버튼
        style.configure("Show.TButton", font=(FONT, 10, "bold"),
                         padding=(14, 7), background=BG,
                         foreground=FG, borderwidth=1, relief="solid")
        style.map("Show.TButton",
                   background=[("active", HOVER)])

        # Quit 버튼
        style.configure("Quit.TButton", font=(FONT, 9),
                         padding=(10, 6), background=SURFACE,
                         foreground="#bb4444", borderwidth=1, relief="solid")
        style.map("Quit.TButton",
                   background=[("active", HOVER)])

        # Treeview
        style.configure("Treeview",
                         background="#ffffff",
                         foreground=FG,
                         fieldbackground="#ffffff",
                         font=(FONT, 9),
                         rowheight=30,
                         borderwidth=1, relief="solid")
        style.configure("Treeview.Heading",
                         background=HEAD_BG,
                         foreground=HEAD_FG,
                         font=(FONT, 9, "bold"),
                         borderwidth=0)
        style.map("Treeview",
                   background=[("selected", SELECT)],
                   foreground=[("selected", "#111111")])

    def _build_ui(self):
        FONT = "Malgun Gothic"
        BG = "#fafaf8"

        # ── 상단 헤더 ──
        header = ttk.Frame(self.root)
        header.pack(fill=tk.X, padx=20, pady=(20, 4))

        ttk.Label(header, text=APP_NAME, style="Title.TLabel").pack(side=tk.LEFT)
        ttk.Label(header, text=f"v{APP_VERSION}", style="Section.TLabel").pack(
            side=tk.LEFT, padx=(8, 0), pady=(6, 0))

        self.btn_restore_all = ttk.Button(header, text="Restore All and Quit",
                                           command=self._on_quit, style="Quit.TButton")
        self.btn_restore_all.pack(side=tk.RIGHT)

        # ── 탭 컨테이너 ──
        self.style = ttk.Style()
        self.style.configure("TNotebook", background=BG, borderwidth=0)
        self.style.configure("TNotebook.Tab", font=(FONT, 10),
                              padding=(16, 6), background="#e6e5e3")
        self.style.map("TNotebook.Tab",
                        background=[("selected", BG)],
                        foreground=[("selected", "#111111")])

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=20, pady=(8, 12))

        # ── Main 탭 ──
        main_tab = ttk.Frame(notebook)
        notebook.add(main_tab, text="  Main  ")
        self._build_main_tab(main_tab)

        # ── Settings 탭 ──
        settings_tab = ttk.Frame(notebook)
        notebook.add(settings_tab, text="  Settings  ")
        self._build_settings_tab(settings_tab)

    def _build_main_tab(self, parent):
        # ── 버튼 바 ──
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, padx=4, pady=(12, 4))

        self.btn_hide = ttk.Button(btn_frame, text="⬇  Hide",
                                    command=self._on_hide, style="Hide.TButton")
        self.btn_hide.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_show = ttk.Button(btn_frame, text="⬆  Show",
                                    command=self._on_show, style="Show.TButton")
        self.btn_show.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_refresh = ttk.Button(btn_frame, text="↻  Refresh",
                                       command=self._refresh_list)
        self.btn_refresh.pack(side=tk.LEFT)

        # ── 실행 중인 창 목록 ──
        ttk.Label(parent, text="VISIBLE WINDOWS",
                   style="Section.TLabel").pack(anchor=tk.W, padx=4, pady=(12, 4))

        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))

        cols = ("hwnd", "process", "title")
        self.tree_visible = ttk.Treeview(tree_frame, columns=cols,
                                          show="headings", selectmode="extended")
        self.tree_visible.heading("hwnd", text="HWND")
        self.tree_visible.heading("process", text="Process")
        self.tree_visible.heading("title", text="Window Title")
        self.tree_visible.column("hwnd", width=80, stretch=False)
        self.tree_visible.column("process", width=160, stretch=False)
        self.tree_visible.column("title", width=420, stretch=True)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL,
                                   command=self.tree_visible.yview)
        self.tree_visible.configure(yscrollcommand=scrollbar.set)
        self.tree_visible.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # ── 숨겨진 창 목록 ──
        ttk.Label(parent, text="HIDDEN WINDOWS",
                   style="Section.TLabel").pack(anchor=tk.W, padx=4, pady=(10, 4))

        hidden_frame = ttk.Frame(parent)
        hidden_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))

        self.tree_hidden = ttk.Treeview(hidden_frame, columns=cols,
                                         show="headings", selectmode="extended")
        self.tree_hidden.heading("hwnd", text="HWND")
        self.tree_hidden.heading("process", text="Process")
        self.tree_hidden.heading("title", text="Window Title")
        self.tree_hidden.column("hwnd", width=80, stretch=False)
        self.tree_hidden.column("process", width=160, stretch=False)
        self.tree_hidden.column("title", width=420, stretch=True)

        scrollbar2 = ttk.Scrollbar(hidden_frame, orient=tk.VERTICAL,
                                    command=self.tree_hidden.yview)
        self.tree_hidden.configure(yscrollcommand=scrollbar2.set)
        self.tree_hidden.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar2.pack(side=tk.RIGHT, fill=tk.Y)

        # ── 상태바 ──
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(parent, textvariable=self.status_var,
                                font=("Malgun Gothic", 8), foreground="#999999")
        status_bar.pack(fill=tk.X, padx=4, pady=(4, 4))

    def _build_settings_tab(self, parent):
        FONT = "Malgun Gothic"
        BG = "#fafaf8"
        FG = "#222222"
        FG_DIM = "#999999"

        container = ttk.Frame(parent)
        container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # ── About ──
        ttk.Label(container, text="ABOUT", style="Section.TLabel").pack(
            anchor=tk.W, pady=(0, 8))

        info_frame = ttk.Frame(container)
        info_frame.pack(fill=tk.X, pady=(0, 20))

        rows = [
            ("App", APP_NAME),
            ("Version", f"v{APP_VERSION}"),
            ("Author", APP_AUTHOR),
            ("License", "MIT"),
        ]
        for label, value in rows:
            row = ttk.Frame(info_frame)
            row.pack(fill=tk.X, pady=2)
            ttk.Label(row, text=label, font=(FONT, 10),
                       foreground=FG_DIM, width=12, anchor=tk.W).pack(side=tk.LEFT)
            ttk.Label(row, text=value, font=(FONT, 10),
                       foreground=FG).pack(side=tk.LEFT)

        # ── 구분선 ──
        sep = ttk.Frame(container, height=1)
        sep.pack(fill=tk.X, pady=(0, 20))
        sep_line = tk.Frame(sep, height=1, bg="#dddcda")
        sep_line.pack(fill=tk.X)

        # ── Update ──
        ttk.Label(container, text="UPDATE", style="Section.TLabel").pack(
            anchor=tk.W, pady=(0, 8))

        self.update_status_var = tk.StringVar(value="")
        update_frame = ttk.Frame(container)
        update_frame.pack(fill=tk.X, pady=(0, 8))

        self.btn_check_update = ttk.Button(
            update_frame, text="Check for Updates",
            command=self._on_check_update)
        self.btn_check_update.pack(side=tk.LEFT, padx=(0, 12))

        self.update_status_label = ttk.Label(
            update_frame, textvariable=self.update_status_var,
            font=(FONT, 9), foreground=FG_DIM)
        self.update_status_label.pack(side=tk.LEFT)

        # ── 구분선 ──
        sep2 = ttk.Frame(container, height=1)
        sep2.pack(fill=tk.X, pady=(12, 20))
        sep_line2 = tk.Frame(sep2, height=1, bg="#dddcda")
        sep_line2.pack(fill=tk.X)

        # ── Links ──
        ttk.Label(container, text="LINKS", style="Section.TLabel").pack(
            anchor=tk.W, pady=(0, 8))

        link_frame = ttk.Frame(container)
        link_frame.pack(fill=tk.X)

        github_btn = ttk.Button(link_frame, text="GitHub Repository",
                                 command=lambda: webbrowser.open(APP_GITHUB))
        github_btn.pack(side=tk.LEFT, padx=(0, 8))

        releases_btn = ttk.Button(link_frame, text="Download Latest",
                                   command=lambda: webbrowser.open(f"{APP_GITHUB}/releases/latest"))
        releases_btn.pack(side=tk.LEFT)

    # ── 업데이트 체크 ──
    def _on_check_update(self):
        """GitHub Releases API로 최신 버전을 확인한다."""
        self.update_status_var.set("Checking...")
        self.btn_check_update.configure(state="disabled")

        def check():
            try:
                url = f"https://api.github.com/repos/{APP_REPO}/releases/latest"
                req = urllib.request.Request(url, headers={"User-Agent": APP_NAME})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode())

                latest = data.get("tag_name", "").lstrip("v")
                if not latest:
                    self.root.after(0, lambda: self._update_result("Could not determine latest version"))
                    return

                if latest == APP_VERSION:
                    self.root.after(0, lambda: self._update_result(
                        f"✓ Up to date (v{APP_VERSION})"))
                else:
                    self.root.after(0, lambda: self._update_result(
                        f"New version available: v{latest}", is_new=True))

            except Exception as e:
                self.root.after(0, lambda: self._update_result(f"Check failed: {e}"))

        threading.Thread(target=check, daemon=True).start()

    def _update_result(self, message: str, is_new: bool = False):
        self.update_status_var.set(message)
        self.btn_check_update.configure(state="normal")
        if is_new:
            self.update_status_label.configure(foreground="#bb4444")

    # ── 시스템 트레이 ──
    def _setup_tray(self):
        """시스템 트레이 아이콘을 생성한다."""
        try:
            import pystray
            from PIL import Image, ImageDraw

            # 16x16 아이콘 생성
            img = Image.new("RGB", (64, 64), "#ffffff")
            draw = ImageDraw.Draw(img)
            draw.rounded_rectangle([8, 8, 56, 56], radius=10, fill="#111111")
            draw.text((20, 14), "S", fill="#ffffff")

            menu = pystray.Menu(
                pystray.MenuItem("Show", self._tray_show, default=True),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Restore All & Quit", self._tray_quit),
            )

            self.tray_icon = pystray.Icon("slink", img, "Slink", menu)
            tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
            tray_thread.start()
        except ImportError:
            # pystray 미설치 시 트레이 없이 동작
            self.tray_icon = None

    def _tray_show(self, icon=None, item=None):
        """트레이에서 창을 다시 표시한다."""
        self.root.after(0, self._restore_window)

    def _restore_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _tray_quit(self, icon=None, item=None):
        """트레이에서 종료한다."""
        self.root.after(0, self._on_quit)

    def _refresh_list(self):
        """창 목록을 새로고침한다."""
        for item in self.tree_visible.get_children():
            self.tree_visible.delete(item)

        windows = enum_taskbar_windows()
        own_hwnd = self.root.winfo_id()

        for w in windows:
            if w["hwnd"] == own_hwnd:
                continue
            if w["hwnd"] in self.core.hidden:
                continue
            self.tree_visible.insert("", tk.END, values=(
                hex(w["hwnd"]), w["process"], w["title"]
            ))

        for item in self.tree_hidden.get_children():
            self.tree_hidden.delete(item)

        for hwnd, info in self.core.hidden.items():
            self.tree_hidden.insert("", tk.END, values=(
                hex(hwnd), info.process, info.title
            ))

        self.status_var.set(
            f"Visible: {len(self.tree_visible.get_children())}  |  "
            f"Hidden: {len(self.core.hidden)}"
        )

    def _on_hide(self):
        """선택한 창을 작업표시줄에서 숨긴다."""
        selected = self.tree_visible.selection()
        if not selected:
            self.status_var.set("⚠ Select a window to hide")
            return

        count = 0
        for item in selected:
            values = self.tree_visible.item(item, "values")
            hwnd = int(values[0], 16)
            process = values[1]
            title = values[2]
            if self.core.hide_from_taskbar(hwnd, title, process):
                count += 1

        self.status_var.set(f"✓ Hidden {count} window(s)")
        self._refresh_list()

    def _on_show(self):
        """선택한 창을 다시 작업표시줄에 표시한다."""
        selected = self.tree_hidden.selection()
        if not selected:
            self.status_var.set("⚠ Select a window to restore")
            return

        count = 0
        for item in selected:
            values = self.tree_hidden.item(item, "values")
            hwnd = int(values[0], 16)
            if self.core.show_on_taskbar(hwnd):
                count += 1

        self.status_var.set(f"✓ Restored {count} window(s)")
        self._refresh_list()

    def _start_watcher(self):
        """1초마다 숨긴 창이 다시 나타났는지 감시하고 다시 숨긴다."""
        def tick():
            if self.core.hidden:
                self.core.enforce_hidden()
            self._watcher_id = self.root.after(1000, tick)
        self._watcher_id = self.root.after(1000, tick)

    def _on_close(self):
        """X 버튼 → 시스템 트레이로 최소화."""
        self.root.withdraw()

    def _on_quit(self):
        """모든 창 복원 후 완전 종료."""
        self.core.restore_all()
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


# ──────────────────────────────────────────────
# 진입점
# ──────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    import platform

    if platform.system() != "Windows":
        print("이 프로그램은 Windows에서만 실행 가능합니다.")
        print("Windows PC에서 다음 명령으로 실행하세요:")
        print()
        print("  pip install -r requirements.txt")
        print("  python slink.py")
        print()
        print(".exe로 패키징하려면:")
        print("  pip install pyinstaller")
        print('  pyinstaller --onefile --windowed --name Slink slink.py')
        sys.exit(1)

    core = SlinkCore()
    gui = SlinkGUI(core)
    gui.run()

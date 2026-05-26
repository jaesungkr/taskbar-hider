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
import sys
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
APP_VERSION = "1.2.0"
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

        # 윈도우 아이콘 설정
        import os
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        ico_path = os.path.join(base_dir, "slink.ico")
        if os.path.exists(ico_path):
            self.root.iconbitmap(ico_path)

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
        FG_DIM = "#aaaaaa"
        SURFACE = "#f0efed"
        HOVER = "#e6e5e3"
        SELECT = "#e0ddd8"
        HEAD_BG = "#e8e7e5"
        HEAD_FG = "#555555"

        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=FG,
                         font=(FONT, 10))
        style.configure("Title.TLabel", font=(FONT, 16, "bold"),
                         foreground="#111111", background=BG)
        style.configure("Section.TLabel", font=(FONT, 9),
                         foreground=FG_DIM, background=BG)

        # 기본 버튼
        style.configure("TButton", font=(FONT, 9), padding=(12, 6),
                         background=SURFACE, foreground=FG,
                         borderwidth=0)
        style.map("TButton",
                   background=[("active", HOVER)])

        # Hide 버튼 — 진한 차콜
        style.configure("Hide.TButton", font=(FONT, 9, "bold"),
                         padding=(16, 7), background="#3a3a3a",
                         foreground="#f0efed", borderwidth=0)
        style.map("Hide.TButton",
                   background=[("active", "#505050")],
                   foreground=[("active", "#f0efed")])

        # Show 버튼 — 테두리만
        style.configure("Show.TButton", font=(FONT, 9, "bold"),
                         padding=(16, 7), background=BG,
                         foreground=FG, borderwidth=1, relief="solid")
        style.map("Show.TButton",
                   background=[("active", HOVER)])

        # Quit 버튼
        style.configure("Quit.TButton", font=(FONT, 8),
                         padding=(10, 5), background=SURFACE,
                         foreground="#cc6666", borderwidth=0)
        style.map("Quit.TButton",
                   background=[("active", HOVER)])

        # Treeview — 부드러운 헤더
        style.configure("Treeview",
                         background="#ffffff",
                         foreground=FG,
                         fieldbackground="#ffffff",
                         font=(FONT, 9),
                         rowheight=28,
                         borderwidth=0)
        style.configure("Treeview.Heading",
                         background=HEAD_BG,
                         foreground=HEAD_FG,
                         font=(FONT, 8),
                         borderwidth=0,
                         relief="flat")
        style.map("Treeview",
                   background=[("selected", SELECT)],
                   foreground=[("selected", "#111111")])
        style.map("Treeview.Heading",
                   background=[("active", "#dddcda")])

    def _build_ui(self):
        FONT = "Malgun Gothic"
        BG = "#fafaf8"

        # ── 상단 헤더 ──
        header = ttk.Frame(self.root)
        header.pack(fill=tk.X, padx=24, pady=(20, 0))

        title_frame = ttk.Frame(header)
        title_frame.pack(side=tk.LEFT)
        ttk.Label(title_frame, text=APP_NAME, style="Title.TLabel").pack(side=tk.LEFT)
        ttk.Label(title_frame, text=f"v{APP_VERSION}",
                   font=(FONT, 9), foreground="#bbbbbb").pack(
            side=tk.LEFT, padx=(6, 0), pady=(6, 0))

        self.btn_restore_all = ttk.Button(header, text="Quit",
                                           command=self._on_quit, style="Quit.TButton")
        self.btn_restore_all.pack(side=tk.RIGHT)

        # ── 자체 탭 바 ──
        tab_bar = tk.Frame(self.root, bg=BG)
        tab_bar.pack(fill=tk.X, padx=24, pady=(12, 0))

        self._tab_buttons = {}
        self._tab_frames = {}
        self._active_tab = None

        for tab_name in ["Main", "Settings"]:
            btn = tk.Label(tab_bar, text=tab_name, font=(FONT, 10),
                           bg=BG, fg="#aaaaaa", cursor="hand2",
                           padx=0, pady=4)
            btn.pack(side=tk.LEFT, padx=(0, 20))
            btn.bind("<Button-1>", lambda e, n=tab_name: self._switch_tab(n))
            self._tab_buttons[tab_name] = btn

        # 탭 하단 구분선
        tk.Frame(self.root, height=1, bg="#e6e5e3").pack(fill=tk.X, padx=24, pady=(4, 0))

        # ── 탭 컨텐츠 영역 ──
        self._tab_container = ttk.Frame(self.root)
        self._tab_container.pack(fill=tk.BOTH, expand=True, padx=24, pady=(0, 12))

        # Main 탭
        main_frame = ttk.Frame(self._tab_container)
        self._tab_frames["Main"] = main_frame
        self._build_main_tab(main_frame)

        # Settings 탭
        settings_frame = ttk.Frame(self._tab_container)
        self._tab_frames["Settings"] = settings_frame
        self._build_settings_tab(settings_frame)

        # 기본 탭 활성화
        self._switch_tab("Main")

    def _switch_tab(self, name: str):
        """자체 탭 전환."""
        if self._active_tab == name:
            return

        # 모든 프레임 숨기기
        for frame in self._tab_frames.values():
            frame.pack_forget()

        # 선택된 프레임 표시
        self._tab_frames[name].pack(fill=tk.BOTH, expand=True)

        # 탭 버튼 스타일 업데이트
        for tab_name, btn in self._tab_buttons.items():
            if tab_name == name:
                btn.configure(fg="#222222", font=("Malgun Gothic", 10, "bold"))
            else:
                btn.configure(fg="#aaaaaa", font=("Malgun Gothic", 10))

        self._active_tab = name

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
        FG = "#222222"
        FG_DIM = "#aaaaaa"
        FG_MID = "#777777"

        container = ttk.Frame(parent)
        container.pack(fill=tk.BOTH, expand=True, padx=4, pady=(16, 4))

        # ── About ──
        ttk.Label(container, text="ABOUT", font=(FONT, 8),
                   foreground=FG_DIM).pack(anchor=tk.W, pady=(0, 10))

        info_frame = ttk.Frame(container)
        info_frame.pack(fill=tk.X, pady=(0, 16))

        rows = [
            ("App", APP_NAME),
            ("Version", f"v{APP_VERSION}"),
            ("Author", APP_AUTHOR),
            ("License", "MIT"),
        ]
        for label, value in rows:
            row = ttk.Frame(info_frame)
            row.pack(fill=tk.X, pady=3)
            ttk.Label(row, text=label, font=(FONT, 9),
                       foreground=FG_MID, width=12, anchor=tk.W).pack(side=tk.LEFT)
            ttk.Label(row, text=value, font=(FONT, 9),
                       foreground=FG).pack(side=tk.LEFT)

        # ── 구분선 ──
        tk.Frame(container, height=1, bg="#e6e5e3").pack(fill=tk.X, pady=(4, 16))

        # ── Update ──
        ttk.Label(container, text="UPDATE", font=(FONT, 8),
                   foreground=FG_DIM).pack(anchor=tk.W, pady=(0, 10))

        self.update_status_var = tk.StringVar(value="")
        update_frame = ttk.Frame(container)
        update_frame.pack(fill=tk.X, pady=(0, 8))

        self.btn_check_update = ttk.Button(
            update_frame, text="Check for Updates",
            command=self._on_check_update)
        self.btn_check_update.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_do_update = ttk.Button(
            update_frame, text="Update Now",
            command=self._on_do_update, style="Hide.TButton")
        self._latest_download_url = None

        self.update_status_label = ttk.Label(
            update_frame, textvariable=self.update_status_var,
            font=(FONT, 9), foreground=FG_DIM)
        self.update_status_label.pack(side=tk.LEFT, padx=(6, 0))

        # ── 구분선 ──
        tk.Frame(container, height=1, bg="#e6e5e3").pack(fill=tk.X, pady=(12, 16))

        # ── Links ──
        ttk.Label(container, text="LINKS", font=(FONT, 8),
                   foreground=FG_DIM).pack(anchor=tk.W, pady=(0, 10))

        link_frame = ttk.Frame(container)
        link_frame.pack(fill=tk.X)

        github_btn = ttk.Button(link_frame, text="GitHub",
                                 command=lambda: webbrowser.open(APP_GITHUB))
        github_btn.pack(side=tk.LEFT, padx=(0, 6))

        releases_btn = ttk.Button(link_frame, text="Releases",
                                   command=lambda: webbrowser.open(f"{APP_GITHUB}/releases/latest"))
        releases_btn.pack(side=tk.LEFT)

    # ── 업데이트 체크 ──
    def _on_check_update(self):
        """GitHub Releases API로 최신 버전을 확인한다."""
        self.update_status_var.set("Checking...")
        self.btn_check_update.configure(state="disabled")
        self._latest_download_url = None

        def check():
            try:
                url = f"https://api.github.com/repos/{APP_REPO}/releases/latest"
                req = urllib.request.Request(url, headers={"User-Agent": APP_NAME})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode())

                latest = data.get("tag_name", "").lstrip("v")
                if not latest:
                    self.root.after(0, lambda: self._update_result(
                        "Could not determine latest version"))
                    return

                # .exe 다운로드 URL 찾기
                download_url = None
                for asset in data.get("assets", []):
                    if asset["name"].lower().endswith(".exe"):
                        download_url = asset["browser_download_url"]
                        break

                if latest == APP_VERSION:
                    self.root.after(0, lambda: self._update_result(
                        f"✓ Up to date (v{APP_VERSION})"))
                else:
                    self.root.after(0, lambda: self._update_result(
                        f"v{latest} available!", is_new=True,
                        download_url=download_url))

            except Exception as e:
                self.root.after(0, lambda: self._update_result(
                    f"Check failed: {e}"))

        threading.Thread(target=check, daemon=True).start()

    def _update_result(self, message: str, is_new: bool = False,
                       download_url: str = None):
        self.update_status_var.set(message)
        self.btn_check_update.configure(state="normal")

        if is_new:
            self.update_status_label.configure(foreground="#bb4444")
            self._latest_download_url = download_url
            if download_url:
                self.btn_do_update.pack(side=tk.LEFT, padx=(6, 0),
                                         before=self.update_status_label)
        else:
            self.update_status_label.configure(foreground="#999999")
            self.btn_do_update.pack_forget()

    def _on_do_update(self):
        """최신 .exe를 다운로드하고 현재 실행 파일을 교체한 뒤 재시작한다."""
        if not self._latest_download_url:
            self.update_status_var.set("No download URL available")
            return

        self.btn_do_update.configure(state="disabled")
        self.update_status_var.set("Downloading...")

        def download_and_replace():
            try:
                import os
                import subprocess
                import tempfile

                current_exe = os.path.abspath(sys.argv[0])
                is_frozen = getattr(sys, 'frozen', False)

                if is_frozen:
                    # .exe로 실행 중 → .exe 교체
                    new_path = current_exe + ".new"
                    old_path = current_exe + ".old"

                    # 다운로드
                    req = urllib.request.Request(
                        self._latest_download_url,
                        headers={"User-Agent": APP_NAME})
                    with urllib.request.urlopen(req, timeout=60) as resp:
                        with open(new_path, "wb") as f:
                            while True:
                                chunk = resp.read(8192)
                                if not chunk:
                                    break
                                f.write(chunk)

                    # 교체 배치 스크립트 생성:
                    # 현재 프로세스 종료 대기 → old로 이름변경 → new를 원래이름으로 → 실행 → old 삭제
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

                    self.root.after(0, lambda: self._execute_update(bat_path))

                else:
                    # .py로 실행 중 → slink.py 교체
                    # GitHub에서 최신 slink.py raw 파일 다운로드
                    raw_url = f"https://raw.githubusercontent.com/{APP_REPO}/master/slink.py"
                    req = urllib.request.Request(
                        raw_url, headers={"User-Agent": APP_NAME})
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        new_code = resp.read()

                    with open(current_exe, "wb") as f:
                        f.write(new_code)

                    self.root.after(0, lambda: self._restart_app())

            except Exception as e:
                self.root.after(0, lambda: self._update_error(str(e)))

        threading.Thread(target=download_and_replace, daemon=True).start()

    def _execute_update(self, bat_path: str):
        """배치 스크립트를 실행하고 앱을 종료한다."""
        import subprocess
        self.core.restore_all()
        if self.tray_icon:
            self.tray_icon.stop()
        subprocess.Popen(["cmd", "/c", bat_path],
                          creationflags=0x00000008)  # DETACHED_PROCESS
        self.root.destroy()
        sys.exit(0)

    def _restart_app(self):
        """현재 앱을 재시작한다. (.py 모드)"""
        import subprocess
        self.core.restore_all()
        if self.tray_icon:
            self.tray_icon.stop()
        subprocess.Popen([sys.executable] + sys.argv)
        self.root.destroy()
        sys.exit(0)

    def _update_error(self, error: str):
        self.update_status_var.set(f"Update failed: {error}")
        self.btn_do_update.configure(state="normal")

    # ── 시스템 트레이 ──
    def _setup_tray(self):
        """시스템 트레이 아이콘을 생성한다."""
        try:
            import pystray
            from PIL import Image
            import os

            # 아이콘 파일 찾기 (exe 번들 또는 스크립트 위치)
            if getattr(sys, 'frozen', False):
                base_dir = os.path.dirname(sys.executable)
            else:
                base_dir = os.path.dirname(os.path.abspath(__file__))

            icon_path = os.path.join(base_dir, "slink.png")

            if os.path.exists(icon_path):
                img = Image.open(icon_path)
            else:
                # 폴백: 간단한 아이콘 생성
                from PIL import ImageDraw
                img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
                draw = ImageDraw.Draw(img)
                draw.ellipse([8, 8, 56, 56], fill="#1a1a1a")

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

"""Slink GUI — polished, production-grade interface."""

import os
import sys
import webbrowser
import tkinter as tk
from tkinter import ttk

from slink import APP_NAME, APP_VERSION, APP_AUTHOR, APP_GITHUB
from slink.core import SlinkCore
from slink.win32 import enum_taskbar_windows
from slink.tray import setup_tray
from slink.updater import check_for_update, download_and_apply
from slink.resources import get_resource_path

# ── 디자인 토큰 ─────────────────────────────────
FONT = "Malgun Gothic"

# 배경 — 아주 미세한 따뜻함
BG       = "#fafaf8"
BG_WHITE = "#ffffff"

# 텍스트
FG       = "#1a1a1a"
FG_SEC   = "#6b6b6b"
FG_MUTED = "#b0b0b0"

# 표면
SURFACE     = "#f2f1ef"
SURFACE_ALT = "#eaeae8"
BORDER      = "#e0dfdd"

# 인터랙션
HOVER    = "#e8e7e5"
SELECT   = "#d8d7d5"

# 액센트
ACCENT      = "#2d2d2d"
ACCENT_HOVER = "#444444"
DANGER      = "#c75050"


class SlinkGUI:
    def __init__(self, core: SlinkCore):
        self.core = core
        self.tray_icon = None
        self._latest_download_url = None

        self._init_window()
        self._apply_style()
        self._build_ui()
        self._refresh_list()
        self._start_watcher()
        self._init_tray()

    # ── 초기화 ───────────────────────────────────

    def _init_window(self):
        self.root = tk.Tk()
        self.root.title("Slink")
        self.root.geometry("700x640")
        self.root.minsize(560, 480)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        ico_path = get_resource_path("slink.ico")
        if os.path.exists(ico_path):
            self.root.iconbitmap(ico_path)

    def _init_tray(self):
        png_path = get_resource_path("slink.png")
        self.tray_icon = setup_tray(
            on_show=lambda *_: self.root.after(0, self._restore_window),
            on_quit=lambda *_: self.root.after(0, self._on_quit),
            icon_path=png_path,
        )

    # ── 스타일 ───────────────────────────────────

    def _apply_style(self):
        s = ttk.Style()
        s.theme_use("clam")

        # 프레임, 라벨
        s.configure("TFrame", background=BG)
        s.configure("TLabel", background=BG, foreground=FG, font=(FONT, 9))

        # 기본 버튼 — 고스트 스타일
        s.configure("TButton", font=(FONT, 9), padding=(14, 6),
                     background=SURFACE, foreground=FG, borderwidth=0,
                     focuscolor=BG)
        s.map("TButton", background=[("active", HOVER), ("disabled", SURFACE)])

        # Primary 버튼 — 진한 채움
        s.configure("Primary.TButton", font=(FONT, 9, "bold"), padding=(18, 7),
                     background=ACCENT, foreground="#ffffff", borderwidth=0,
                     focuscolor=ACCENT)
        s.map("Primary.TButton",
              background=[("active", ACCENT_HOVER), ("disabled", "#888888")],
              foreground=[("active", "#ffffff"), ("disabled", "#cccccc")])

        # Secondary 버튼 — 테두리
        s.configure("Secondary.TButton", font=(FONT, 9), padding=(18, 7),
                     background=BG, foreground=FG, borderwidth=1,
                     relief="solid", focuscolor=BG)
        s.map("Secondary.TButton", background=[("active", SURFACE)])

        # Danger 텍스트 버튼
        s.configure("Danger.TButton", font=(FONT, 8), padding=(8, 4),
                     background=BG, foreground=DANGER, borderwidth=0,
                     focuscolor=BG)
        s.map("Danger.TButton", background=[("active", SURFACE)])

        # Treeview — 미니멀
        s.configure("Treeview", background=BG_WHITE, foreground=FG,
                     fieldbackground=BG_WHITE, font=(FONT, 9),
                     rowheight=30, borderwidth=0)
        s.configure("Treeview.Heading", background=SURFACE,
                     foreground=FG_SEC, font=(FONT, 8),
                     borderwidth=0, relief="flat", padding=(8, 4))
        s.map("Treeview",
              background=[("selected", SELECT)],
              foreground=[("selected", FG)])
        s.map("Treeview.Heading",
              background=[("active", SURFACE_ALT)])

        # Scrollbar — 얇고 미니멀
        s.configure("Vertical.TScrollbar", background=SURFACE,
                     troughcolor=BG_WHITE, borderwidth=0, width=8)

    # ── UI 빌드 ──────────────────────────────────

    def _build_ui(self):
        pad_x = 28

        # ── 헤더 ──
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill=tk.X, padx=pad_x, pady=(24, 0))

        tk.Label(header, text=APP_NAME, font=(FONT, 18, "bold"),
                 fg=FG, bg=BG).pack(side=tk.LEFT)
        tk.Label(header, text=f"v{APP_VERSION}", font=(FONT, 9),
                 fg=FG_MUTED, bg=BG).pack(side=tk.LEFT, padx=(8, 0), pady=(7, 0))

        ttk.Button(header, text="× Quit", command=self._on_quit,
                    style="Danger.TButton").pack(side=tk.RIGHT)

        # ── 탭 바 ──
        tab_bar = tk.Frame(self.root, bg=BG)
        tab_bar.pack(fill=tk.X, padx=pad_x, pady=(16, 0))

        self._tab_buttons = {}
        self._tab_underlines = {}
        self._tab_frames = {}
        self._active_tab = None

        for name in ["Main", "Settings"]:
            tab_container = tk.Frame(tab_bar, bg=BG)
            tab_container.pack(side=tk.LEFT, padx=(0, 24))

            btn = tk.Label(tab_container, text=name, font=(FONT, 10),
                           bg=BG, fg=FG_MUTED, cursor="hand2", pady=6)
            btn.pack()
            btn.bind("<Button-1>", lambda e, n=name: self._switch_tab(n))

            underline = tk.Frame(tab_container, height=2, bg=BG)
            underline.pack(fill=tk.X)

            self._tab_buttons[name] = btn
            self._tab_underlines[name] = underline

        # 구분선
        tk.Frame(self.root, height=1, bg=BORDER).pack(fill=tk.X, padx=pad_x)

        # ── 탭 콘텐츠 ──
        self._tab_container = tk.Frame(self.root, bg=BG)
        self._tab_container.pack(fill=tk.BOTH, expand=True, padx=pad_x, pady=(0, 16))

        main_frame = tk.Frame(self._tab_container, bg=BG)
        self._tab_frames["Main"] = main_frame
        self._build_main_tab(main_frame)

        settings_frame = tk.Frame(self._tab_container, bg=BG)
        self._tab_frames["Settings"] = settings_frame
        self._build_settings_tab(settings_frame)

        self._switch_tab("Main")

    def _switch_tab(self, name: str):
        if self._active_tab == name:
            return
        for frame in self._tab_frames.values():
            frame.pack_forget()
        self._tab_frames[name].pack(fill=tk.BOTH, expand=True)

        for tab_name in self._tab_buttons:
            btn = self._tab_buttons[tab_name]
            line = self._tab_underlines[tab_name]
            if tab_name == name:
                btn.configure(fg=FG, font=(FONT, 10, "bold"))
                line.configure(bg=ACCENT)
            else:
                btn.configure(fg=FG_MUTED, font=(FONT, 10))
                line.configure(bg=BG)

        self._active_tab = name

    # ── Main 탭 ──────────────────────────────────

    def _build_main_tab(self, parent):
        # 액션 바
        actions = tk.Frame(parent, bg=BG)
        actions.pack(fill=tk.X, pady=(16, 0))

        ttk.Button(actions, text="Hide", command=self._on_hide,
                    style="Primary.TButton").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(actions, text="Show", command=self._on_show,
                    style="Secondary.TButton").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(actions, text="Refresh",
                    command=self._refresh_list).pack(side=tk.LEFT)

        # Visible
        self._section_label(parent, "Visible", top=16)

        frame1 = ttk.Frame(parent)
        frame1.pack(fill=tk.BOTH, expand=True, pady=(0, 4))
        self.tree_visible = self._make_tree(frame1)

        # Hidden
        self._section_label(parent, "Hidden", top=8)

        frame2 = ttk.Frame(parent)
        frame2.pack(fill=tk.BOTH, expand=True, pady=(0, 4))
        self.tree_hidden = self._make_tree(frame2)

        # Status
        self.status_var = tk.StringVar(value="Ready")
        tk.Label(parent, textvariable=self.status_var, font=(FONT, 8),
                 fg=FG_MUTED, bg=BG, anchor=tk.W).pack(fill=tk.X, pady=(4, 0))

    def _section_label(self, parent, text, top=12):
        tk.Label(parent, text=text.upper(), font=(FONT, 8),
                 fg=FG_MUTED, bg=BG, anchor=tk.W).pack(
            fill=tk.X, pady=(top, 4))

    def _make_tree(self, parent):
        cols = ("process", "title")
        tree = ttk.Treeview(parent, columns=cols, show="headings",
                             selectmode="extended")
        tree.heading("process", text="Process", anchor=tk.W)
        tree.heading("title", text="Window", anchor=tk.W)
        tree.column("process", width=150, stretch=False)
        tree.column("title", width=480, stretch=True)

        sb = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        return tree

    # ── Settings 탭 ──────────────────────────────

    def _build_settings_tab(self, parent):
        c = tk.Frame(parent, bg=BG)
        c.pack(fill=tk.BOTH, expand=True, pady=(20, 0))

        # About
        self._section_label(c, "About", top=0)
        info = tk.Frame(c, bg=BG)
        info.pack(fill=tk.X, pady=(0, 16))
        for label, value in [("App", APP_NAME), ("Version", f"v{APP_VERSION}"),
                              ("Author", APP_AUTHOR), ("License", "MIT")]:
            row = tk.Frame(info, bg=BG)
            row.pack(fill=tk.X, pady=2)
            tk.Label(row, text=label, font=(FONT, 9), fg=FG_SEC,
                     bg=BG, width=10, anchor=tk.W).pack(side=tk.LEFT)
            tk.Label(row, text=value, font=(FONT, 9), fg=FG,
                     bg=BG).pack(side=tk.LEFT)

        tk.Frame(c, height=1, bg=BORDER).pack(fill=tk.X, pady=(0, 16))

        # Update
        self._section_label(c, "Update", top=0)
        self.update_status_var = tk.StringVar(value="")

        uf = tk.Frame(c, bg=BG)
        uf.pack(fill=tk.X, pady=(0, 8))

        self.btn_check_update = ttk.Button(
            uf, text="Check for Updates", command=self._on_check_update)
        self.btn_check_update.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_do_update = ttk.Button(
            uf, text="Update Now", command=self._on_do_update,
            style="Primary.TButton")

        self.update_status_label = tk.Label(
            uf, textvariable=self.update_status_var,
            font=(FONT, 9), fg=FG_MUTED, bg=BG)
        self.update_status_label.pack(side=tk.LEFT, padx=(4, 0))

        tk.Frame(c, height=1, bg=BORDER).pack(fill=tk.X, pady=(12, 16))

        # Links
        self._section_label(c, "Links", top=0)
        lf = tk.Frame(c, bg=BG)
        lf.pack(fill=tk.X)
        ttk.Button(lf, text="GitHub",
                    command=lambda: webbrowser.open(APP_GITHUB)).pack(
            side=tk.LEFT, padx=(0, 8))
        ttk.Button(lf, text="Releases",
                    command=lambda: webbrowser.open(
                        f"{APP_GITHUB}/releases/latest")).pack(side=tk.LEFT)

    # ── 이벤트 핸들러 ────────────────────────────

    def _refresh_list(self):
        for item in self.tree_visible.get_children():
            self.tree_visible.delete(item)
        windows = enum_taskbar_windows()
        own_hwnd = self.root.winfo_id()
        for w in windows:
            if w["hwnd"] == own_hwnd or w["hwnd"] in self.core.hidden:
                continue
            # Slink 자신은 목록에서 제외
            proc = w["process"].lower()
            if proc.startswith("slink") and proc.endswith(".exe"):
                continue
            self.tree_visible.insert("", tk.END,
                iid=hex(w["hwnd"]),
                values=(w["process"], w["title"]))

        for item in self.tree_hidden.get_children():
            self.tree_hidden.delete(item)
        for hwnd, info in self.core.hidden.items():
            self.tree_hidden.insert("", tk.END,
                iid=hex(hwnd),
                values=(info.process, info.title))

        v = len(self.tree_visible.get_children())
        h = len(self.core.hidden)
        self.status_var.set(f"{v} visible  ·  {h} hidden")

    def _on_hide(self):
        selected = self.tree_visible.selection()
        if not selected:
            self.status_var.set("Select a window to hide")
            return
        count = 0
        for iid in selected:
            hwnd = int(iid, 16)
            vals = self.tree_visible.item(iid, "values")
            if self.core.hide_from_taskbar(hwnd, vals[1], vals[0]):
                count += 1
        self.status_var.set(f"Hidden {count} window(s)")
        self._refresh_list()

    def _on_show(self):
        selected = self.tree_hidden.selection()
        if not selected:
            self.status_var.set("Select a window to restore")
            return
        count = 0
        for iid in selected:
            hwnd = int(iid, 16)
            if self.core.show_on_taskbar(hwnd):
                count += 1
        self.status_var.set(f"Restored {count} window(s)")
        self._refresh_list()

    def _start_watcher(self):
        def tick():
            if self.core.hidden:
                self.core.enforce_hidden()
            self.root.after(1000, tick)
        self.root.after(1000, tick)

    def _on_close(self):
        self.root.withdraw()

    def _restore_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _on_quit(self):
        self.core.restore_all()
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.destroy()

    # ── 업데이트 ─────────────────────────────────

    def _on_check_update(self):
        self.update_status_var.set("Checking...")
        self.btn_check_update.configure(state="disabled")

        def callback(latest, download_url, error):
            if error:
                self.root.after(0, lambda: self._show_update_result(
                    f"Failed: {error}"))
            elif download_url:
                self.root.after(0, lambda: self._show_update_result(
                    f"v{latest} available", is_new=True,
                    download_url=download_url))
            else:
                self.root.after(0, lambda: self._show_update_result(
                    f"Up to date"))

        check_for_update(callback)

    def _show_update_result(self, msg, is_new=False, download_url=None):
        self.update_status_var.set(msg)
        self.btn_check_update.configure(state="normal")
        if is_new:
            self.update_status_label.configure(fg=DANGER)
            self._latest_download_url = download_url
            if download_url:
                self.btn_do_update.pack(side=tk.LEFT, padx=(8, 0),
                                         before=self.update_status_label)
        else:
            self.update_status_label.configure(fg=FG_MUTED)
            self.btn_do_update.pack_forget()

    def _on_do_update(self):
        if not self._latest_download_url:
            return
        self.btn_do_update.configure(state="disabled")
        self.update_status_var.set("Downloading...")

        def on_done(close_func):
            def _do():
                from tkinter import messagebox
                self.core.restore_all()
                if self.tray_icon:
                    self.tray_icon.stop()
                messagebox.showinfo("Slink", "Update complete. Please restart Slink.")
                close_func()
            self.root.after(0, _do)

        def on_error(msg):
            self.root.after(0, lambda: self._update_error(msg))

        download_and_apply(self._latest_download_url, on_done, on_error)

    def _update_error(self, error: str):
        self.update_status_var.set(f"Failed: {error}")
        self.btn_do_update.configure(state="normal")

    # ── 실행 ─────────────────────────────────────

    def run(self):
        self.root.mainloop()

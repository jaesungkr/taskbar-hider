"""Slink GUI — Main window, tabs, and event handling."""

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

FONT = "Malgun Gothic"
BG = "#fafaf8"
FG = "#222222"
FG_DIM = "#aaaaaa"
FG_MID = "#777777"
SURFACE = "#f0efed"
HOVER = "#e6e5e3"
SELECT = "#e0ddd8"


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

    # ── 초기화 ──────────────────────────────────

    def _init_window(self):
        self.root = tk.Tk()
        self.root.title("Slink")
        self.root.geometry("720x700")
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

    # ── 스타일 ──────────────────────────────────

    def _apply_style(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=FG, font=(FONT, 10))
        style.configure("Title.TLabel", font=(FONT, 16, "bold"),
                         foreground="#111111", background=BG)

        style.configure("TButton", font=(FONT, 9), padding=(12, 6),
                         background=SURFACE, foreground=FG, borderwidth=0)
        style.map("TButton", background=[("active", HOVER)])

        style.configure("Hide.TButton", font=(FONT, 9, "bold"),
                         padding=(16, 7), background="#3a3a3a",
                         foreground="#f0efed", borderwidth=0)
        style.map("Hide.TButton",
                   background=[("active", "#505050")],
                   foreground=[("active", "#f0efed")])

        style.configure("Show.TButton", font=(FONT, 9, "bold"),
                         padding=(16, 7), background=BG,
                         foreground=FG, borderwidth=1, relief="solid")
        style.map("Show.TButton", background=[("active", HOVER)])

        style.configure("Quit.TButton", font=(FONT, 8), padding=(10, 5),
                         background=SURFACE, foreground="#cc6666", borderwidth=0)
        style.map("Quit.TButton", background=[("active", HOVER)])

        style.configure("Treeview", background="#ffffff", foreground=FG,
                         fieldbackground="#ffffff", font=(FONT, 9),
                         rowheight=28, borderwidth=0)
        style.configure("Treeview.Heading", background="#e8e7e5",
                         foreground="#555555", font=(FONT, 8),
                         borderwidth=0, relief="flat")
        style.map("Treeview",
                   background=[("selected", SELECT)],
                   foreground=[("selected", "#111111")])
        style.map("Treeview.Heading", background=[("active", "#dddcda")])

    # ── UI 빌드 ─────────────────────────────────

    def _build_ui(self):
        # 헤더
        header = ttk.Frame(self.root)
        header.pack(fill=tk.X, padx=24, pady=(20, 0))

        title_frame = ttk.Frame(header)
        title_frame.pack(side=tk.LEFT)
        ttk.Label(title_frame, text=APP_NAME, style="Title.TLabel").pack(side=tk.LEFT)
        ttk.Label(title_frame, text=f"v{APP_VERSION}",
                   font=(FONT, 9), foreground="#bbbbbb").pack(
            side=tk.LEFT, padx=(6, 0), pady=(6, 0))

        ttk.Button(header, text="Quit", command=self._on_quit,
                    style="Quit.TButton").pack(side=tk.RIGHT)

        # 탭 바
        tab_bar = tk.Frame(self.root, bg=BG)
        tab_bar.pack(fill=tk.X, padx=24, pady=(12, 0))

        self._tab_buttons = {}
        self._tab_frames = {}
        self._active_tab = None

        for name in ["Main", "Settings"]:
            btn = tk.Label(tab_bar, text=name, font=(FONT, 10),
                           bg=BG, fg=FG_DIM, cursor="hand2", padx=0, pady=4)
            btn.pack(side=tk.LEFT, padx=(0, 20))
            btn.bind("<Button-1>", lambda e, n=name: self._switch_tab(n))
            self._tab_buttons[name] = btn

        tk.Frame(self.root, height=1, bg=HOVER).pack(fill=tk.X, padx=24, pady=(4, 0))

        self._tab_container = ttk.Frame(self.root)
        self._tab_container.pack(fill=tk.BOTH, expand=True, padx=24, pady=(0, 12))

        main_frame = ttk.Frame(self._tab_container)
        self._tab_frames["Main"] = main_frame
        self._build_main_tab(main_frame)

        settings_frame = ttk.Frame(self._tab_container)
        self._tab_frames["Settings"] = settings_frame
        self._build_settings_tab(settings_frame)

        self._switch_tab("Main")

    def _switch_tab(self, name: str):
        if self._active_tab == name:
            return
        for frame in self._tab_frames.values():
            frame.pack_forget()
        self._tab_frames[name].pack(fill=tk.BOTH, expand=True)
        for tab_name, btn in self._tab_buttons.items():
            if tab_name == name:
                btn.configure(fg=FG, font=(FONT, 10, "bold"))
            else:
                btn.configure(fg=FG_DIM, font=(FONT, 10))
        self._active_tab = name

    def _build_main_tab(self, parent):
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, padx=4, pady=(12, 4))

        ttk.Button(btn_frame, text="⬇  Hide", command=self._on_hide,
                    style="Hide.TButton").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_frame, text="⬆  Show", command=self._on_show,
                    style="Show.TButton").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_frame, text="↻  Refresh",
                    command=self._refresh_list).pack(side=tk.LEFT)

        # Visible windows
        ttk.Label(parent, text="VISIBLE WINDOWS", font=(FONT, 8),
                   foreground=FG_DIM).pack(anchor=tk.W, padx=4, pady=(12, 4))

        cols = ("hwnd", "process", "title")

        frame1 = ttk.Frame(parent)
        frame1.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))
        self.tree_visible = self._make_tree(frame1, cols)

        # Hidden windows
        ttk.Label(parent, text="HIDDEN WINDOWS", font=(FONT, 8),
                   foreground=FG_DIM).pack(anchor=tk.W, padx=4, pady=(10, 4))

        frame2 = ttk.Frame(parent)
        frame2.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))
        self.tree_hidden = self._make_tree(frame2, cols)

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(parent, textvariable=self.status_var,
                   font=(FONT, 8), foreground=FG_DIM).pack(
            fill=tk.X, padx=4, pady=(4, 4))

    def _make_tree(self, parent, cols):
        tree = ttk.Treeview(parent, columns=cols,
                             show="headings", selectmode="extended")
        tree.heading("hwnd", text="HWND")
        tree.heading("process", text="Process")
        tree.heading("title", text="Window Title")
        tree.column("hwnd", width=80, stretch=False)
        tree.column("process", width=160, stretch=False)
        tree.column("title", width=420, stretch=True)

        sb = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        return tree

    def _build_settings_tab(self, parent):
        container = ttk.Frame(parent)
        container.pack(fill=tk.BOTH, expand=True, padx=4, pady=(16, 4))

        # About
        ttk.Label(container, text="ABOUT", font=(FONT, 8),
                   foreground=FG_DIM).pack(anchor=tk.W, pady=(0, 10))

        info_frame = ttk.Frame(container)
        info_frame.pack(fill=tk.X, pady=(0, 16))
        for label, value in [("App", APP_NAME), ("Version", f"v{APP_VERSION}"),
                              ("Author", APP_AUTHOR), ("License", "MIT")]:
            row = ttk.Frame(info_frame)
            row.pack(fill=tk.X, pady=3)
            ttk.Label(row, text=label, font=(FONT, 9), foreground=FG_MID,
                       width=12, anchor=tk.W).pack(side=tk.LEFT)
            ttk.Label(row, text=value, font=(FONT, 9),
                       foreground=FG).pack(side=tk.LEFT)

        tk.Frame(container, height=1, bg=HOVER).pack(fill=tk.X, pady=(4, 16))

        # Update
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

        self.update_status_label = ttk.Label(
            update_frame, textvariable=self.update_status_var,
            font=(FONT, 9), foreground=FG_DIM)
        self.update_status_label.pack(side=tk.LEFT, padx=(6, 0))

        tk.Frame(container, height=1, bg=HOVER).pack(fill=tk.X, pady=(12, 16))

        # Links
        ttk.Label(container, text="LINKS", font=(FONT, 8),
                   foreground=FG_DIM).pack(anchor=tk.W, pady=(0, 10))

        link_frame = ttk.Frame(container)
        link_frame.pack(fill=tk.X)
        ttk.Button(link_frame, text="GitHub",
                    command=lambda: webbrowser.open(APP_GITHUB)).pack(
            side=tk.LEFT, padx=(0, 6))
        ttk.Button(link_frame, text="Releases",
                    command=lambda: webbrowser.open(
                        f"{APP_GITHUB}/releases/latest")).pack(side=tk.LEFT)

    # ── 이벤트 핸들러 ───────────────────────────

    def _refresh_list(self):
        for item in self.tree_visible.get_children():
            self.tree_visible.delete(item)
        windows = enum_taskbar_windows()
        own_hwnd = self.root.winfo_id()
        for w in windows:
            if w["hwnd"] == own_hwnd or w["hwnd"] in self.core.hidden:
                continue
            self.tree_visible.insert("", tk.END, values=(
                hex(w["hwnd"]), w["process"], w["title"]))

        for item in self.tree_hidden.get_children():
            self.tree_hidden.delete(item)
        for hwnd, info in self.core.hidden.items():
            self.tree_hidden.insert("", tk.END, values=(
                hex(hwnd), info.process, info.title))

        self.status_var.set(
            f"Visible: {len(self.tree_visible.get_children())}  |  "
            f"Hidden: {len(self.core.hidden)}")

    def _on_hide(self):
        selected = self.tree_visible.selection()
        if not selected:
            self.status_var.set("⚠ Select a window to hide")
            return
        count = 0
        for item in selected:
            vals = self.tree_visible.item(item, "values")
            if self.core.hide_from_taskbar(int(vals[0], 16), vals[2], vals[1]):
                count += 1
        self.status_var.set(f"✓ Hidden {count} window(s)")
        self._refresh_list()

    def _on_show(self):
        selected = self.tree_hidden.selection()
        if not selected:
            self.status_var.set("⚠ Select a window to restore")
            return
        count = 0
        for item in selected:
            vals = self.tree_hidden.item(item, "values")
            if self.core.show_on_taskbar(int(vals[0], 16)):
                count += 1
        self.status_var.set(f"✓ Restored {count} window(s)")
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

    # ── 업데이트 ────────────────────────────────

    def _on_check_update(self):
        self.update_status_var.set("Checking...")
        self.btn_check_update.configure(state="disabled")

        def callback(latest, download_url, error):
            if error:
                self.root.after(0, lambda: self._show_update_result(
                    f"Check failed: {error}"))
            elif download_url:
                self.root.after(0, lambda: self._show_update_result(
                    f"v{latest} available!", is_new=True,
                    download_url=download_url))
            else:
                self.root.after(0, lambda: self._show_update_result(
                    f"✓ Up to date (v{APP_VERSION})"))

        check_for_update(callback)

    def _show_update_result(self, msg, is_new=False, download_url=None):
        self.update_status_var.set(msg)
        self.btn_check_update.configure(state="normal")
        if is_new:
            self.update_status_label.configure(foreground="#bb4444")
            self._latest_download_url = download_url
            if download_url:
                self.btn_do_update.pack(side=tk.LEFT, padx=(6, 0),
                                         before=self.update_status_label)
        else:
            self.update_status_label.configure(foreground=FG_DIM)
            self.btn_do_update.pack_forget()

    def _on_do_update(self):
        if not self._latest_download_url:
            self.update_status_var.set("No download URL available")
            return

        self.btn_do_update.configure(state="disabled")
        self.update_status_var.set("Downloading...")

        def on_done(restart_func):
            def _do():
                self.core.restore_all()
                if self.tray_icon:
                    self.tray_icon.stop()
                restart_func()
            self.root.after(0, _do)

        def on_error(msg):
            self.root.after(0, lambda: self._update_error(msg))

        download_and_apply(self._latest_download_url, on_done, on_error)

    def _update_error(self, error: str):
        self.update_status_var.set(f"Update failed: {error}")
        self.btn_do_update.configure(state="normal")

    # ── 실행 ────────────────────────────────────

    def run(self):
        self.root.mainloop()

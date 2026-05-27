"""Slink GUI — Award-level CustomTkinter interface."""

import os
import sys
import webbrowser
import customtkinter as ctk

from slink import APP_NAME, APP_VERSION, APP_AUTHOR, APP_GITHUB
from slink.core import SlinkCore
from slink.win32 import enum_taskbar_windows
from slink.tray import setup_tray
from slink.updater import check_for_update, download_and_apply
from slink.resources import get_resource_path

# ── 테마 ──────────────────────────────────────
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

F = "Malgun Gothic"
BG       = "#fafaf8"
CARD     = "#ffffff"
FG       = "#1a1a1a"
FG2      = "#666666"
FG3      = "#aaaaaa"
BORDER   = "#ebebeb"
HOVER    = "#f5f5f3"
SELECT   = "#eeedeb"
ACCENT   = "#1a1a1a"
ACCENT_H = "#333333"
DANGER   = "#d45555"
SUCCESS  = "#3d8c5c"
DIVIDER  = "#f0f0ee"


class SlinkGUI:
    def __init__(self, core: SlinkCore):
        self.core = core
        self.tray_icon = None
        self._latest_download_url = None
        self._selected_visible = set()
        self._selected_hidden = set()

        self._init_window()
        self._build_ui()
        self._refresh_list()
        self._start_watcher()
        self._init_tray()

    def _init_window(self):
        self.root = ctk.CTk()
        self.root.title("Slink")
        self.root.geometry("620x580")
        self.root.minsize(480, 420)
        self.root.configure(fg_color=BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        ico = get_resource_path("slink.ico")
        if os.path.exists(ico):
            self.root.iconbitmap(ico)
            self.root.after(200, lambda: self.root.iconbitmap(ico))

    def _init_tray(self):
        png = get_resource_path("slink.png")
        self.tray_icon = setup_tray(
            on_show=lambda *_: self.root.after(0, self._restore_window),
            on_quit=lambda *_: self.root.after(0, self._on_quit),
            icon_path=png)

    # ── 레이아웃 ─────────────────────────────────

    def _build_ui(self):
        # 사이드바 + 콘텐츠 구조
        wrapper = ctk.CTkFrame(self.root, fg_color=BG)
        wrapper.pack(fill="both", expand=True, padx=28, pady=(20, 20))

        # ── 헤더 ──
        header = ctk.CTkFrame(wrapper, fg_color=BG)
        header.pack(fill="x", pady=(0, 16))

        left = ctk.CTkFrame(header, fg_color=BG)
        left.pack(side="left")

        ctk.CTkLabel(left, text="Slink", font=(F, 24, "bold"),
                     text_color=FG).pack(side="left")
        ctk.CTkLabel(left, text=APP_VERSION, font=(F, 10),
                     text_color=FG3).pack(side="left", padx=(10, 0), pady=(10, 0))

        # 탭 + Quit을 우측에
        right = ctk.CTkFrame(header, fg_color=BG)
        right.pack(side="right")

        self._tabs = {}
        self._active_tab = None

        for name in ["Windows", "Settings"]:
            btn = ctk.CTkButton(right, text=name, width=70, height=28,
                                 font=(F, 11), corner_radius=14,
                                 fg_color="transparent", text_color=FG3,
                                 hover_color=HOVER,
                                 command=lambda n=name: self._switch_tab(n))
            btn.pack(side="left", padx=(0, 4))
            self._tabs[name] = btn

        ctk.CTkFrame(right, width=1, height=20,
                      fg_color=BORDER).pack(side="left", padx=(8, 8))

        ctk.CTkButton(right, text="Quit", width=48, height=28,
                       font=(F, 10), corner_radius=14,
                       fg_color="transparent", text_color=DANGER,
                       hover_color="#fdf0f0",
                       command=self._on_quit).pack(side="left")

        # 구분선
        ctk.CTkFrame(wrapper, height=1, fg_color=BORDER).pack(fill="x")

        # ── 페이지 컨테이너 ──
        self._page_container = ctk.CTkFrame(wrapper, fg_color=BG)
        self._page_container.pack(fill="both", expand=True, pady=(16, 0))

        self._pages = {}

        win_page = ctk.CTkFrame(self._page_container, fg_color=BG)
        self._pages["Windows"] = win_page
        self._build_windows_page(win_page)

        set_page = ctk.CTkFrame(self._page_container, fg_color=BG)
        self._pages["Settings"] = set_page
        self._build_settings_page(set_page)

        self._switch_tab("Windows")

    def _switch_tab(self, name):
        if self._active_tab == name:
            return
        for page in self._pages.values():
            page.pack_forget()
        self._pages[name].pack(fill="both", expand=True)
        for n, btn in self._tabs.items():
            if n == name:
                btn.configure(fg_color=ACCENT, text_color="#ffffff",
                              hover_color=ACCENT_H)
            else:
                btn.configure(fg_color="transparent", text_color=FG3,
                              hover_color=HOVER)
        self._active_tab = name

    # ── Windows 페이지 ───────────────────────────

    def _build_windows_page(self, parent):
        # 액션 바
        bar = ctk.CTkFrame(parent, fg_color=BG)
        bar.pack(fill="x", pady=(0, 12))

        ctk.CTkButton(bar, text="↓  Hide", width=88, height=30,
                       font=(F, 11, "bold"), corner_radius=6,
                       fg_color=ACCENT, hover_color=ACCENT_H,
                       command=self._on_hide).pack(side="left", padx=(0, 6))

        ctk.CTkButton(bar, text="↑  Show", width=88, height=30,
                       font=(F, 11), corner_radius=6,
                       fg_color="transparent", text_color=FG,
                       border_width=1, border_color=BORDER,
                       hover_color=HOVER,
                       command=self._on_show).pack(side="left", padx=(0, 6))

        ctk.CTkButton(bar, text="↻", width=32, height=30,
                       font=(F, 13), corner_radius=6,
                       fg_color="transparent", text_color=FG3,
                       hover_color=HOVER,
                       command=self._refresh_list).pack(side="left")

        self.status_label = ctk.CTkLabel(bar, text="",
                                          font=(F, 10), text_color=FG3)
        self.status_label.pack(side="right")

        # ── Visible 섹션 ──
        ctk.CTkLabel(parent, text="VISIBLE", font=(F, 9, "bold"),
                     text_color=FG3).pack(anchor="w", pady=(0, 4))

        self.visible_card = ctk.CTkFrame(parent, fg_color=CARD,
                                          corner_radius=10,
                                          border_width=1, border_color=BORDER)
        self.visible_card.pack(fill="both", expand=True, pady=(0, 10))

        self.visible_scroll = ctk.CTkScrollableFrame(
            self.visible_card, fg_color=CARD, corner_radius=10,
            scrollbar_button_color=BORDER,
            scrollbar_button_hover_color="#d0d0d0")
        self.visible_scroll.pack(fill="both", expand=True, padx=1, pady=1)

        # ── Hidden 섹션 ──
        ctk.CTkLabel(parent, text="HIDDEN", font=(F, 9, "bold"),
                     text_color=FG3).pack(anchor="w", pady=(0, 4))

        self.hidden_card = ctk.CTkFrame(parent, fg_color=CARD,
                                         corner_radius=10,
                                         border_width=1, border_color=BORDER)
        self.hidden_card.pack(fill="both", expand=True)

        self.hidden_scroll = ctk.CTkScrollableFrame(
            self.hidden_card, fg_color=CARD, corner_radius=10,
            scrollbar_button_color=BORDER,
            scrollbar_button_hover_color="#d0d0d0")
        self.hidden_scroll.pack(fill="both", expand=True, padx=1, pady=1)

    # ── Settings 페이지 ──────────────────────────

    def _build_settings_page(self, parent):
        # About
        about = self._card(parent)
        self._card_title(about, "About")
        for k, v in [("App", APP_NAME), ("Version", f"v{APP_VERSION}"),
                      ("Author", APP_AUTHOR), ("License", "MIT")]:
            self._info_row(about, k, v)

        # Update
        update = self._card(parent, top=10)
        self._card_title(update, "Update")

        row = ctk.CTkFrame(update, fg_color=CARD)
        row.pack(fill="x", pady=(0, 2))

        self.btn_check = ctk.CTkButton(
            row, text="Check for Updates", width=130, height=28,
            font=(F, 10), corner_radius=6,
            fg_color="transparent", text_color=FG,
            border_width=1, border_color=BORDER,
            hover_color=HOVER,
            command=self._on_check_update)
        self.btn_check.pack(side="left", padx=(0, 6))

        self.btn_update = ctk.CTkButton(
            row, text="Update Now", width=90, height=28,
            font=(F, 10, "bold"), corner_radius=6,
            fg_color=ACCENT, hover_color=ACCENT_H,
            command=self._on_do_update)

        self.lbl_update = ctk.CTkLabel(
            row, text="", font=(F, 10), text_color=FG3)
        self.lbl_update.pack(side="left", padx=(4, 0))

        # Links
        links = self._card(parent, top=10)
        self._card_title(links, "Links")
        ctk.CTkButton(links, text="View Releases →", width=110, height=26,
                       font=(F, 10), corner_radius=6,
                       fg_color="transparent", text_color=FG2,
                       hover_color=HOVER,
                       command=lambda: webbrowser.open(
                           f"{APP_GITHUB}/releases/latest")).pack(anchor="w")

    def _card(self, parent, top=0):
        card = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=10,
                             border_width=1, border_color=BORDER)
        card.pack(fill="x", pady=(top, 0))
        inner = ctk.CTkFrame(card, fg_color=CARD)
        inner.pack(fill="x", padx=18, pady=14)
        return inner

    def _card_title(self, parent, text):
        ctk.CTkLabel(parent, text=text, font=(F, 12, "bold"),
                     text_color=FG).pack(anchor="w", pady=(0, 8))

    def _info_row(self, parent, label, value):
        row = ctk.CTkFrame(parent, fg_color=CARD)
        row.pack(fill="x", pady=1)
        ctk.CTkLabel(row, text=label, font=(F, 10),
                     text_color=FG3, width=70, anchor="w").pack(side="left")
        ctk.CTkLabel(row, text=value, font=(F, 10),
                     text_color=FG).pack(side="left")

    # ── 리스트 아이템 ────────────────────────────

    def _make_row(self, parent, hwnd, process, title, sel_set, is_last=False):
        row = ctk.CTkFrame(parent, fg_color=CARD, height=34, corner_radius=0)
        row.pack(fill="x", padx=6, pady=0)
        row.pack_propagate(False)

        # 선택 인디케이터
        indicator = ctk.CTkFrame(row, width=3, height=20,
                                  fg_color=CARD, corner_radius=2)
        indicator.pack(side="left", padx=(4, 8), pady=7)

        p = ctk.CTkLabel(row, text=process, font=(F, 10),
                          text_color=FG2, width=120, anchor="w")
        p.pack(side="left", padx=(0, 6))

        t = ctk.CTkLabel(row, text=title, font=(F, 10),
                          text_color=FG, anchor="w")
        t.pack(side="left", fill="x", expand=True, padx=(0, 10))

        if not is_last:
            div = ctk.CTkFrame(parent, height=1, fg_color=DIVIDER)
            div.pack(fill="x", padx=14)

        def select(e=None):
            if hwnd in sel_set:
                sel_set.discard(hwnd)
                row.configure(fg_color=CARD)
                indicator.configure(fg_color=CARD)
            else:
                sel_set.add(hwnd)
                row.configure(fg_color=SELECT)
                indicator.configure(fg_color=ACCENT)

        def enter(e=None):
            if hwnd not in sel_set:
                row.configure(fg_color=HOVER)

        def leave(e=None):
            if hwnd not in sel_set:
                row.configure(fg_color=CARD)

        for w in [row, p, t, indicator]:
            w.bind("<Button-1>", select)
            w.bind("<Enter>", enter)
            w.bind("<Leave>", leave)

    # ── 이벤트 ───────────────────────────────────

    def _refresh_list(self):
        self._selected_visible.clear()
        self._selected_hidden.clear()

        for w in self.visible_scroll.winfo_children():
            w.destroy()
        for w in self.hidden_scroll.winfo_children():
            w.destroy()

        windows = enum_taskbar_windows()
        own = self.root.winfo_id()
        visible = []
        for w in windows:
            if w["hwnd"] == own or w["hwnd"] in self.core.hidden:
                continue
            proc = w["process"].lower()
            if proc.startswith("slink") and proc.endswith(".exe"):
                continue
            visible.append(w)

        for i, w in enumerate(visible):
            self._make_row(self.visible_scroll, w["hwnd"],
                           w["process"], w["title"],
                           self._selected_visible,
                           is_last=(i == len(visible) - 1))

        hidden_list = list(self.core.hidden.items())
        for i, (hwnd, info) in enumerate(hidden_list):
            self._make_row(self.hidden_scroll, hwnd,
                           info.process, info.title,
                           self._selected_hidden,
                           is_last=(i == len(hidden_list) - 1))

        self.status_label.configure(
            text=f"{len(visible)} visible  ·  {len(hidden_list)} hidden")

    def _on_hide(self):
        if not self._selected_visible:
            self.status_label.configure(text="Select a window to hide")
            return
        c = 0
        for hwnd in list(self._selected_visible):
            w = [x for x in enum_taskbar_windows() if x["hwnd"] == hwnd]
            if w:
                if self.core.hide_from_taskbar(hwnd, w[0]["title"], w[0]["process"]):
                    c += 1
        self.status_label.configure(text=f"Hidden {c} window(s)")
        self._refresh_list()

    def _on_show(self):
        if not self._selected_hidden:
            self.status_label.configure(text="Select a window to restore")
            return
        c = 0
        for hwnd in list(self._selected_hidden):
            if self.core.show_on_taskbar(hwnd):
                c += 1
        self.status_label.configure(text=f"Restored {c} window(s)")
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
        self.lbl_update.configure(text="Checking...", text_color=FG3)
        self.btn_check.configure(state="disabled")

        def cb(latest, url, err):
            if err:
                self.root.after(0, lambda: self._update_result(f"Failed", False))
            elif url:
                self.root.after(0, lambda: self._update_result(
                    f"v{latest} available", True, url))
            else:
                self.root.after(0, lambda: self._update_result("Up to date", False))

        check_for_update(cb)

    def _update_result(self, msg, is_new, url=None):
        self.lbl_update.configure(text=msg)
        self.btn_check.configure(state="normal")
        if is_new:
            self.lbl_update.configure(text_color=DANGER)
            self._latest_download_url = url
            if url:
                self.btn_update.pack(side="left", padx=(6, 0),
                                      before=self.lbl_update)
        else:
            self.lbl_update.configure(text_color=SUCCESS)
            self.btn_update.pack_forget()

    def _on_do_update(self):
        if not self._latest_download_url:
            return
        self.btn_update.configure(state="disabled")
        self.lbl_update.configure(text="Downloading...", text_color=FG3)

        def on_done(close_func):
            def _do():
                self.core.restore_all()
                if self.tray_icon:
                    self.tray_icon.stop()
                close_func()
            self.root.after(0, _do)

        def on_error(msg):
            self.root.after(0, lambda: self._update_fail(msg))

        download_and_apply(self._latest_download_url, on_done, on_error)

    def _update_fail(self, err):
        self.lbl_update.configure(text=f"Failed: {err}", text_color=DANGER)
        self.btn_update.configure(state="normal")

    def run(self):
        self.root.mainloop()

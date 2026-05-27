"""Slink GUI — CustomTkinter modern interface."""

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

# ── 테마 설정 ─────────────────────────────────
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

FONT_FAMILY = "Malgun Gothic"
BG = "#fafaf8"
CARD_BG = "#ffffff"
FG = "#1a1a1a"
FG_SEC = "#777777"
FG_MUTED = "#aaaaaa"
BORDER = "#e8e7e5"
ACCENT = "#2d2d2d"
DANGER = "#c75050"
SUCCESS = "#4a9e6a"
SUCCESS = "#4a9e6a"


class SlinkGUI:
    def __init__(self, core: SlinkCore):
        self.core = core
        self.tray_icon = None
        self._latest_download_url = None

        self._init_window()
        self._build_ui()
        self._refresh_list()
        self._start_watcher()
        self._init_tray()

    # ── 초기화 ───────────────────────────────────

    def _init_window(self):
        self.root = ctk.CTk()
        self.root.title("Slink")
        self.root.geometry("680x620")
        self.root.minsize(520, 460)
        self.root.configure(fg_color=BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        ico_path = get_resource_path("slink.ico")
        if os.path.exists(ico_path):
            self.root.iconbitmap(ico_path)
            self.root.after(200, lambda: self.root.iconbitmap(ico_path))

    def _init_tray(self):
        png_path = get_resource_path("slink.png")
        self.tray_icon = setup_tray(
            on_show=lambda *_: self.root.after(0, self._restore_window),
            on_quit=lambda *_: self.root.after(0, self._on_quit),
            icon_path=png_path,
        )

    # ── UI 빌드 ──────────────────────────────────

    def _build_ui(self):
        # ── 헤더 ──
        header = ctk.CTkFrame(self.root, fg_color=BG)
        header.pack(fill="x", padx=24, pady=(20, 0))

        title_frame = ctk.CTkFrame(header, fg_color=BG)
        title_frame.pack(side="left")

        ctk.CTkLabel(title_frame, text=APP_NAME,
                     font=(FONT_FAMILY, 22, "bold"),
                     text_color=FG).pack(side="left")
        ctk.CTkLabel(title_frame, text=f"v{APP_VERSION}",
                     font=(FONT_FAMILY, 11),
                     text_color=FG_MUTED).pack(side="left", padx=(8, 0), pady=(8, 0))

        ctk.CTkButton(header, text="Quit", width=60, height=28,
                       font=(FONT_FAMILY, 11),
                       fg_color="transparent", text_color=DANGER,
                       hover_color="#fce8e8",
                       command=self._on_quit).pack(side="right")

        # ── 탭 ──
        self.tabview = ctk.CTkTabview(self.root, fg_color=BG,
                                       segmented_button_fg_color=BORDER,
                                       segmented_button_selected_color=ACCENT,
                                       segmented_button_selected_hover_color="#444444",
                                       segmented_button_unselected_color=BORDER,
                                       segmented_button_unselected_hover_color="#d5d4d2",
                                       text_color="white",
                                       corner_radius=8)
        self.tabview.pack(fill="both", expand=True, padx=24, pady=(8, 16))

        tab_windows = self.tabview.add("Windows")
        tab_settings = self.tabview.add("Settings")

        self._build_windows_tab(tab_windows)
        self._build_settings_tab(tab_settings)

    # ── Windows 탭 ───────────────────────────────

    def _build_windows_tab(self, parent):
        # 액션 바
        actions = ctk.CTkFrame(parent, fg_color="transparent")
        actions.pack(fill="x", pady=(4, 8))

        ctk.CTkButton(actions, text="Hide", width=90, height=32,
                       font=(FONT_FAMILY, 12, "bold"),
                       fg_color=ACCENT, hover_color="#444444",
                       corner_radius=6,
                       command=self._on_hide).pack(side="left", padx=(0, 6))

        ctk.CTkButton(actions, text="Show", width=90, height=32,
                       font=(FONT_FAMILY, 12),
                       fg_color="transparent", text_color=FG,
                       border_width=1, border_color=BORDER,
                       hover_color="#f0efed",
                       corner_radius=6,
                       command=self._on_show).pack(side="left", padx=(0, 6))

        ctk.CTkButton(actions, text="Refresh", width=80, height=32,
                       font=(FONT_FAMILY, 11),
                       fg_color="transparent", text_color=FG_SEC,
                       hover_color="#f0efed",
                       corner_radius=6,
                       command=self._refresh_list).pack(side="left")

        # ── Visible 카드 ──
        ctk.CTkLabel(parent, text="VISIBLE", font=(FONT_FAMILY, 10),
                     text_color=FG_MUTED).pack(anchor="w", pady=(4, 2))

        visible_card = ctk.CTkFrame(parent, fg_color=CARD_BG,
                                     corner_radius=8, border_width=1,
                                     border_color=BORDER)
        visible_card.pack(fill="both", expand=True, pady=(0, 8))

        self.visible_scroll = ctk.CTkScrollableFrame(
            visible_card, fg_color=CARD_BG, corner_radius=8)
        self.visible_scroll.pack(fill="both", expand=True, padx=2, pady=2)

        # ── Hidden 카드 ──
        ctk.CTkLabel(parent, text="HIDDEN", font=(FONT_FAMILY, 10),
                     text_color=FG_MUTED).pack(anchor="w", pady=(0, 2))

        hidden_card = ctk.CTkFrame(parent, fg_color=CARD_BG,
                                    corner_radius=8, border_width=1,
                                    border_color=BORDER)
        hidden_card.pack(fill="both", expand=True, pady=(0, 4))

        self.hidden_scroll = ctk.CTkScrollableFrame(
            hidden_card, fg_color=CARD_BG, corner_radius=8)
        self.hidden_scroll.pack(fill="both", expand=True, padx=2, pady=2)

        # 상태바
        self.status_label = ctk.CTkLabel(parent, text="Ready",
                                          font=(FONT_FAMILY, 10),
                                          text_color=FG_MUTED)
        self.status_label.pack(anchor="w", pady=(4, 0))

        # 선택 추적
        self._visible_items = {}
        self._hidden_items = {}
        self._selected_visible = set()
        self._selected_hidden = set()

    # ── Settings 탭 ──────────────────────────────

    def _build_settings_tab(self, parent):
        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.pack(fill="both", expand=True, pady=(4, 0))

        # About 카드
        about_card = ctk.CTkFrame(container, fg_color=CARD_BG,
                                   corner_radius=8, border_width=1,
                                   border_color=BORDER)
        about_card.pack(fill="x", pady=(0, 12))

        about_inner = ctk.CTkFrame(about_card, fg_color=CARD_BG)
        about_inner.pack(fill="x", padx=16, pady=14)

        ctk.CTkLabel(about_inner, text="About",
                     font=(FONT_FAMILY, 11, "bold"),
                     text_color=FG).pack(anchor="w", pady=(0, 8))

        for label, value in [("App", APP_NAME), ("Version", f"v{APP_VERSION}"),
                              ("Author", APP_AUTHOR), ("License", "MIT")]:
            row = ctk.CTkFrame(about_inner, fg_color=CARD_BG)
            row.pack(fill="x", pady=1)
            ctk.CTkLabel(row, text=label, font=(FONT_FAMILY, 11),
                         text_color=FG_SEC, width=80,
                         anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=value, font=(FONT_FAMILY, 11),
                         text_color=FG).pack(side="left")

        # Update 카드
        update_card = ctk.CTkFrame(container, fg_color=CARD_BG,
                                    corner_radius=8, border_width=1,
                                    border_color=BORDER)
        update_card.pack(fill="x", pady=(0, 12))

        update_inner = ctk.CTkFrame(update_card, fg_color=CARD_BG)
        update_inner.pack(fill="x", padx=16, pady=14)

        ctk.CTkLabel(update_inner, text="Update",
                     font=(FONT_FAMILY, 11, "bold"),
                     text_color=FG).pack(anchor="w", pady=(0, 8))

        update_row = ctk.CTkFrame(update_inner, fg_color=CARD_BG)
        update_row.pack(fill="x")

        self.btn_check_update = ctk.CTkButton(
            update_row, text="Check for Updates",
            width=140, height=30,
            font=(FONT_FAMILY, 11),
            fg_color="transparent", text_color=FG,
            border_width=1, border_color=BORDER,
            hover_color="#f0efed", corner_radius=6,
            command=self._on_check_update)
        self.btn_check_update.pack(side="left", padx=(0, 8))

        self.btn_do_update = ctk.CTkButton(
            update_row, text="Update Now",
            width=100, height=30,
            font=(FONT_FAMILY, 11, "bold"),
            fg_color=ACCENT, hover_color="#444444",
            corner_radius=6,
            command=self._on_do_update)

        self.update_status_label = ctk.CTkLabel(
            update_row, text="",
            font=(FONT_FAMILY, 11), text_color=FG_MUTED)
        self.update_status_label.pack(side="left", padx=(4, 0))

        # Links 카드
        links_card = ctk.CTkFrame(container, fg_color=CARD_BG,
                                   corner_radius=8, border_width=1,
                                   border_color=BORDER)
        links_card.pack(fill="x")

        links_inner = ctk.CTkFrame(links_card, fg_color=CARD_BG)
        links_inner.pack(fill="x", padx=16, pady=14)

        ctk.CTkLabel(links_inner, text="Links",
                     font=(FONT_FAMILY, 11, "bold"),
                     text_color=FG).pack(anchor="w", pady=(0, 8))

        ctk.CTkButton(links_inner, text="Releases",
                       width=80, height=28,
                       font=(FONT_FAMILY, 11),
                       fg_color="transparent", text_color=FG_SEC,
                       hover_color="#f0efed", corner_radius=6,
                       command=lambda: webbrowser.open(
                           f"{APP_GITHUB}/releases/latest")).pack(anchor="w")

    # ── 윈도우 목록 아이템 ────────────────────────

    def _create_window_row(self, parent, hwnd, process, title, selected_set):
        """클릭 가능한 윈도우 행을 생성한다."""
        row = ctk.CTkFrame(parent, fg_color=CARD_BG, height=36,
                            corner_radius=4)
        row.pack(fill="x", padx=4, pady=1)
        row.pack_propagate(False)

        proc_label = ctk.CTkLabel(row, text=process,
                                   font=(FONT_FAMILY, 10),
                                   text_color=FG_SEC, width=130, anchor="w")
        proc_label.pack(side="left", padx=(8, 4))

        title_label = ctk.CTkLabel(row, text=title,
                                    font=(FONT_FAMILY, 10),
                                    text_color=FG, anchor="w")
        title_label.pack(side="left", fill="x", expand=True, padx=(0, 8))

        def on_click(event=None):
            if hwnd in selected_set:
                selected_set.discard(hwnd)
                row.configure(fg_color=CARD_BG)
            else:
                selected_set.add(hwnd)
                row.configure(fg_color="#e8e7e5")

        def on_enter(event=None):
            if hwnd not in selected_set:
                row.configure(fg_color="#f4f3f1")

        def on_leave(event=None):
            if hwnd not in selected_set:
                row.configure(fg_color=CARD_BG)

        for widget in [row, proc_label, title_label]:
            widget.bind("<Button-1>", on_click)
            widget.bind("<Enter>", on_enter)
            widget.bind("<Leave>", on_leave)

        return row

    # ── 이벤트 핸들러 ────────────────────────────

    def _refresh_list(self):
        self._selected_visible.clear()
        self._selected_hidden.clear()

        for widget in self.visible_scroll.winfo_children():
            widget.destroy()
        for widget in self.hidden_scroll.winfo_children():
            widget.destroy()

        self._visible_items = {}
        self._hidden_items = {}

        windows = enum_taskbar_windows()
        own_hwnd = self.root.winfo_id()

        for w in windows:
            if w["hwnd"] == own_hwnd or w["hwnd"] in self.core.hidden:
                continue
            proc = w["process"].lower()
            if proc.startswith("slink") and proc.endswith(".exe"):
                continue
            row = self._create_window_row(
                self.visible_scroll, w["hwnd"],
                w["process"], w["title"],
                self._selected_visible)
            self._visible_items[w["hwnd"]] = row

        for hwnd, info in self.core.hidden.items():
            row = self._create_window_row(
                self.hidden_scroll, hwnd,
                info.process, info.title,
                self._selected_hidden)
            self._hidden_items[hwnd] = row

        v = len(self._visible_items)
        h = len(self._hidden_items)
        self.status_label.configure(text=f"{v} visible  ·  {h} hidden")

    def _on_hide(self):
        if not self._selected_visible:
            self.status_label.configure(text="Select a window to hide")
            return
        count = 0
        for hwnd in list(self._selected_visible):
            row = self._visible_items.get(hwnd)
            if row:
                vals = [w.cget("text") for w in row.winfo_children()]
                process = vals[0] if vals else "unknown"
                title = vals[1] if len(vals) > 1 else ""
                if self.core.hide_from_taskbar(hwnd, title, process):
                    count += 1
        self.status_label.configure(text=f"Hidden {count} window(s)")
        self._refresh_list()

    def _on_show(self):
        if not self._selected_hidden:
            self.status_label.configure(text="Select a window to restore")
            return
        count = 0
        for hwnd in list(self._selected_hidden):
            if self.core.show_on_taskbar(hwnd):
                count += 1
        self.status_label.configure(text=f"Restored {count} window(s)")
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
        self.update_status_label.configure(text="Checking...", text_color=FG_MUTED)
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
                    "Up to date"))

        check_for_update(callback)

    def _show_update_result(self, msg, is_new=False, download_url=None):
        self.update_status_label.configure(text=msg)
        self.btn_check_update.configure(state="normal")
        if is_new:
            self.update_status_label.configure(text_color=DANGER)
            self._latest_download_url = download_url
            if download_url:
                self.btn_do_update.pack(side="left", padx=(8, 0),
                                         before=self.update_status_label)
        else:
            self.update_status_label.configure(text_color=SUCCESS)
            self.btn_do_update.pack_forget()

    def _on_do_update(self):
        if not self._latest_download_url:
            return
        self.btn_do_update.configure(state="disabled")
        self.update_status_label.configure(text="Downloading...", text_color=FG_MUTED)

        def on_done(close_func):
            def _do():
                self.core.restore_all()
                if self.tray_icon:
                    self.tray_icon.stop()
                close_func()
            self.root.after(0, _do)

        def on_error(msg):
            self.root.after(0, lambda: self._update_error(msg))

        download_and_apply(self._latest_download_url, on_done, on_error)

    def _update_error(self, error: str):
        self.update_status_label.configure(text=f"Failed: {error}", text_color=DANGER)
        self.btn_do_update.configure(state="normal")

    # ── 실행 ─────────────────────────────────────

    def run(self):
        self.root.mainloop()

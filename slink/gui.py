"""Slink GUI — Canvas-drawn list for zero resize lag."""

import os
import tkinter as tk
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
BG       = "#f5f5f3"
CARD     = "#ffffff"
FG       = "#1a1a1a"
FG2      = "#888888"
FG3      = "#aaaaaa"
BORDER   = "#e4e4e2"
HOVER    = "#f0efed"
SELECT   = "#e8e7e5"
ACCENT   = "#1a1a1a"
ACCENT_H = "#333333"
DANGER   = "#c94444"
SUCCESS  = "#3d8c5c"
DIVIDER  = "#eeeeec"
INDICATOR = "#1a1a1a"

ROW_H = 32


# ── Canvas 리스트 (위젯 0개, 즉각 리사이즈) ───

class CanvasList(tk.Frame):
    """순수 Canvas에 텍스트로 행을 그리는 리스트.

    위젯을 전혀 사용하지 않으므로 리사이즈 시 relayout이 없다.
    """

    def __init__(self, master, on_selection_change=None, **kw):
        super().__init__(master, bg=CARD, highlightthickness=0, bd=0, **kw)

        self._rows = []       # [(hwnd, process, title), ...]
        self._selected = set()  # {hwnd, ...}
        self._hover_idx = -1
        self._on_sel = on_selection_change

        self._canvas = tk.Canvas(self, bg=CARD, highlightthickness=0,
                                 bd=0, relief="flat")
        self._canvas.pack(fill="both", expand=True)

        self._canvas.bind("<Configure>", self._redraw)
        self._canvas.bind("<Button-1>", self._on_click)
        self._canvas.bind("<Motion>", self._on_motion)
        self._canvas.bind("<Leave>", self._on_leave)
        self._canvas.bind("<MouseWheel>", self._on_mousewheel)

    @property
    def selected(self):
        return set(self._selected)

    def set_rows(self, rows):
        """rows: list of (hwnd, process, title)"""
        self._rows = list(rows)
        self._selected.clear()
        self._hover_idx = -1
        self._redraw()

    def _idx_at_y(self, y):
        # Canvas 스크롤 위치를 고려한 실제 y 계산
        canvas_y = self._canvas.canvasy(y)
        idx = int(canvas_y // ROW_H)
        if 0 <= idx < len(self._rows):
            return idx
        return -1

    def _redraw(self, _=None):
        c = self._canvas
        c.delete("all")
        w = c.winfo_width()
        if w < 2:
            w = 500  # 초기값

        total_h = max(len(self._rows) * ROW_H, 1)
        c.configure(scrollregion=(0, 0, w, total_h))

        proc_x = 14      # 프로세스 시작 x
        title_x = 140     # 타이틀 시작 x

        for i, (hwnd, proc, title) in enumerate(self._rows):
            y0 = i * ROW_H
            y1 = y0 + ROW_H
            ymid = y0 + ROW_H // 2

            # 배경
            if hwnd in self._selected:
                bg = SELECT
            elif i == self._hover_idx:
                bg = HOVER
            else:
                bg = CARD

            c.create_rectangle(0, y0, w, y1, fill=bg, outline="", tags=f"row{i}")

            # 선택 인디케이터
            if hwnd in self._selected:
                c.create_rectangle(5, y0 + 8, 8, y1 - 8,
                                   fill=INDICATOR, outline="")

            # 프로세스명 (흐린 색, 작은 텍스트)
            display_proc = proc.replace(".exe", "")
            c.create_text(proc_x, ymid, text=display_proc,
                          anchor="w", fill=FG2,
                          font=(F, 9))

            # 타이틀 (진한 색) — 너비 제한 + 말줄임
            max_title_w = w - title_x - 14
            display_title = self._truncate(title, max_title_w, (F, 10))
            c.create_text(title_x, ymid, text=display_title,
                          anchor="w", fill=FG,
                          font=(F, 10))

            # 구분선
            if i < len(self._rows) - 1:
                c.create_line(14, y1, w - 14, y1, fill=DIVIDER)

    def _truncate(self, text, max_px, font_tuple):
        """텍스트를 max_px에 맞게 말줄임."""
        import tkinter.font as tkfont
        try:
            f = tkfont.Font(family=font_tuple[0], size=font_tuple[1])
            if f.measure(text) <= max_px:
                return text
            while len(text) > 1 and f.measure(text + "…") > max_px:
                text = text[:-1]
            return text + "…"
        except Exception:
            # 폰트 측정 실패 시 문자 수로 대충 자름
            approx = max(int(max_px / 8), 10)
            if len(text) > approx:
                return text[:approx - 1] + "…"
            return text

    def _on_click(self, event):
        idx = self._idx_at_y(event.y)
        if idx < 0:
            return
        hwnd = self._rows[idx][0]
        if hwnd in self._selected:
            self._selected.discard(hwnd)
        else:
            self._selected.add(hwnd)
        self._redraw()
        if self._on_sel:
            self._on_sel()

    def _on_motion(self, event):
        idx = self._idx_at_y(event.y)
        if idx != self._hover_idx:
            self._hover_idx = idx
            self._redraw()

    def _on_leave(self, _=None):
        if self._hover_idx >= 0:
            self._hover_idx = -1
            self._redraw()

    def _on_mousewheel(self, event):
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


# ── 메인 GUI ─────────────────────────────────

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

    def _init_window(self):
        self.root = ctk.CTk()
        self.root.title("Slink")
        self.root.geometry("560x500")
        self.root.minsize(420, 360)
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
        wrapper = ctk.CTkFrame(self.root, fg_color=BG)
        wrapper.pack(fill="both", expand=True, padx=20, pady=(16, 16))

        # ── 헤더 ──
        header = ctk.CTkFrame(wrapper, fg_color=BG)
        header.pack(fill="x", pady=(0, 12))

        left = ctk.CTkFrame(header, fg_color=BG)
        left.pack(side="left")

        ctk.CTkLabel(left, text="Slink", font=(F, 18, "bold"),
                     text_color=FG).pack(side="left")
        ctk.CTkLabel(left, text=f"v{APP_VERSION}", font=(F, 9),
                     text_color=FG3).pack(side="left", padx=(8, 0), pady=(5, 0))

        right = ctk.CTkFrame(header, fg_color=BG)
        right.pack(side="right")

        self._tabs = {}
        self._active_tab = None

        for name in ["Windows", "Settings"]:
            btn = ctk.CTkButton(right, text=name, width=68, height=28,
                                 font=(F, 10), corner_radius=14,
                                 fg_color="transparent", text_color=FG3,
                                 hover_color=HOVER,
                                 command=lambda n=name: self._switch_tab(n))
            btn.pack(side="left", padx=(0, 2))
            self._tabs[name] = btn

        ctk.CTkFrame(right, width=1, height=18,
                      fg_color=BORDER).pack(side="left", padx=(8, 8))

        ctk.CTkButton(right, text="Quit", width=44, height=28,
                       font=(F, 10), corner_radius=14,
                       fg_color="transparent", text_color=DANGER,
                       hover_color="#fdf0f0",
                       command=self._on_quit).pack(side="left")

        # ── 페이지 컨테이너 ──
        self._page_container = ctk.CTkFrame(wrapper, fg_color=BG)
        self._page_container.pack(fill="both", expand=True)

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
        bar.pack(fill="x", pady=(0, 10))

        ctk.CTkButton(bar, text="↓  Hide", width=80, height=30,
                       font=(F, 10, "bold"), corner_radius=6,
                       fg_color=ACCENT, hover_color=ACCENT_H,
                       command=self._on_hide).pack(side="left", padx=(0, 4))

        ctk.CTkButton(bar, text="↑  Show", width=80, height=30,
                       font=(F, 10), corner_radius=6,
                       fg_color="transparent", text_color=FG,
                       border_width=1, border_color=BORDER,
                       hover_color=HOVER,
                       command=self._on_show).pack(side="left", padx=(0, 4))

        ctk.CTkButton(bar, text="↻", width=30, height=30,
                       font=(F, 12), corner_radius=6,
                       fg_color="transparent", text_color=FG3,
                       hover_color=HOVER,
                       command=self._refresh_list).pack(side="left")

        self.status_label = ctk.CTkLabel(bar, text="",
                                          font=(F, 9), text_color=FG3)
        self.status_label.pack(side="right")

        # ── Visible ──
        vis_header = ctk.CTkFrame(parent, fg_color=BG)
        vis_header.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(vis_header, text="VISIBLE", font=(F, 8),
                     text_color=FG3).pack(side="left")
        self.vis_count = ctk.CTkLabel(vis_header, text="0", font=(F, 8),
                                       text_color=FG3)
        self.vis_count.pack(side="right")

        vis_card = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=8,
                                 border_width=1, border_color=BORDER)
        vis_card.pack(fill="both", expand=True, pady=(0, 10))

        self.visible_list = CanvasList(vis_card)
        self.visible_list.pack(fill="both", expand=True, padx=1, pady=1)

        # ── Hidden ──
        hid_header = ctk.CTkFrame(parent, fg_color=BG)
        hid_header.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(hid_header, text="HIDDEN", font=(F, 8),
                     text_color=FG3).pack(side="left")
        self.hid_count = ctk.CTkLabel(hid_header, text="0", font=(F, 8),
                                       text_color=FG3)
        self.hid_count.pack(side="right")

        hid_card = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=8,
                                 border_width=1, border_color=BORDER)
        hid_card.pack(fill="both", expand=True)

        self.hidden_list = CanvasList(hid_card)
        self.hidden_list.pack(fill="both", expand=True, padx=1, pady=1)

    # ── Settings 페이지 ──────────────────────────

    def _build_settings_page(self, parent):
        about = self._card(parent)
        self._card_title(about, "About")
        for k, v in [("App", APP_NAME), ("Version", f"v{APP_VERSION}"),
                      ("Author", APP_AUTHOR), ("License", "MIT")]:
            self._info_row(about, k, v)

        update = self._card(parent, top=8)
        self._card_title(update, "Update")

        row = ctk.CTkFrame(update, fg_color=CARD)
        row.pack(fill="x", pady=(0, 2))

        self.btn_check = ctk.CTkButton(
            row, text="Check for Updates", width=120, height=26,
            font=(F, 10), corner_radius=6,
            fg_color="transparent", text_color=FG,
            border_width=1, border_color=BORDER,
            hover_color=HOVER,
            command=self._on_check_update)
        self.btn_check.pack(side="left", padx=(0, 4))

        self.btn_update = ctk.CTkButton(
            row, text="Update Now", width=84, height=26,
            font=(F, 10, "bold"), corner_radius=6,
            fg_color=ACCENT, hover_color=ACCENT_H,
            command=self._on_do_update)

        self.lbl_update = ctk.CTkLabel(
            row, text="", font=(F, 10), text_color=FG3)
        self.lbl_update.pack(side="left", padx=(4, 0))

        links = self._card(parent, top=8)
        self._card_title(links, "Links")
        ctk.CTkButton(links, text="GitHub Releases →", width=120, height=24,
                       font=(F, 10), corner_radius=6,
                       fg_color="transparent", text_color=FG2,
                       hover_color=HOVER,
                       command=lambda: webbrowser.open(
                           f"{APP_GITHUB}/releases/latest")).pack(anchor="w")

    def _card(self, parent, top=0):
        card = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=8,
                             border_width=1, border_color=BORDER)
        card.pack(fill="x", pady=(top, 0))
        inner = ctk.CTkFrame(card, fg_color=CARD)
        inner.pack(fill="x", padx=14, pady=10)
        return inner

    def _card_title(self, parent, text):
        ctk.CTkLabel(parent, text=text, font=(F, 11, "bold"),
                     text_color=FG).pack(anchor="w", pady=(0, 6))

    def _info_row(self, parent, label, value):
        row = ctk.CTkFrame(parent, fg_color=CARD)
        row.pack(fill="x", pady=1)
        ctk.CTkLabel(row, text=label, font=(F, 10),
                     text_color=FG3, width=60, anchor="w").pack(side="left")
        ctk.CTkLabel(row, text=value, font=(F, 10),
                     text_color=FG).pack(side="left")

    # ── 이벤트 ───────────────────────────────────

    def _refresh_list(self):
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

        vis_rows = [(w["hwnd"], w["process"], w["title"]) for w in visible]
        self.visible_list.set_rows(vis_rows)

        hidden_list = list(self.core.hidden.items())
        hid_rows = [(hwnd, info.process, info.title) for hwnd, info in hidden_list]
        self.hidden_list.set_rows(hid_rows)

        self.vis_count.configure(text=str(len(vis_rows)))
        self.hid_count.configure(text=str(len(hid_rows)))
        self.status_label.configure(
            text=f"{len(vis_rows)} visible  ·  {len(hid_rows)} hidden")

    def _on_hide(self):
        sel = self.visible_list.selected
        if not sel:
            self.status_label.configure(text="Select a window to hide")
            return
        c = 0
        for hwnd in sel:
            w = [x for x in enum_taskbar_windows() if x["hwnd"] == hwnd]
            if w:
                if self.core.hide_from_taskbar(hwnd, w[0]["title"], w[0]["process"]):
                    c += 1
        self.status_label.configure(text=f"Hidden {c} window(s)")
        self._refresh_list()

    def _on_show(self):
        sel = self.hidden_list.selected
        if not sel:
            self.status_label.configure(text="Select a window to restore")
            return
        c = 0
        for hwnd in sel:
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
                self.root.after(0, lambda: self._update_result("Failed", False))
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

"""Core logic for hiding and restoring windows."""

from dataclasses import dataclass
from typing import Dict

from slink.win32 import (
    user32, SW_HIDE, SW_SHOW,
    WS_EX_APPWINDOW, WS_EX_TOOLWINDOW,
    get_window_exstyle, set_window_exstyle, get_window_text,
    get_window_pid, find_all_windows_by_pid, is_window_visible,
    create_taskbar_list,
)


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

        target_pid = get_window_pid(hwnd)
        sibling_hwnds = find_all_windows_by_pid(target_pid)

        for h in sibling_hwnds:
            if h in self.hidden:
                continue

            original_style = get_window_exstyle(h)
            h_title = get_window_text(h) or f"(child of {process})"

            user32.ShowWindow(h, SW_HIDE)
            new_style = (original_style & ~WS_EX_APPWINDOW) | WS_EX_TOOLWINDOW
            set_window_exstyle(h, new_style)
            user32.ShowWindow(h, SW_HIDE)

            if self.taskbar_list:
                try:
                    self.taskbar_list.DeleteTab(h)
                except Exception:
                    pass

            self.hidden[h] = HiddenWindow(
                hwnd=h, title=h_title,
                process=process, original_exstyle=original_style,
            )

        return True

    def show_on_taskbar(self, hwnd: int) -> bool:
        """숨겨진 창을 복원하고 작업표시줄에 다시 표시한다."""
        if hwnd not in self.hidden:
            return False

        info = self.hidden[hwnd]
        set_window_exstyle(hwnd, info.original_exstyle)
        user32.ShowWindow(hwnd, SW_SHOW)

        if self.taskbar_list:
            try:
                self.taskbar_list.AddTab(hwnd)
            except Exception:
                pass

        del self.hidden[hwnd]
        return True

    def enforce_hidden(self):
        """숨긴 창이 다시 나타났으면 다시 숨긴다."""
        for hwnd, info in list(self.hidden.items()):
            if not user32.IsWindow(hwnd):
                del self.hidden[hwnd]
                continue

            current_style = get_window_exstyle(hwnd)
            has_toolwindow = bool(current_style & WS_EX_TOOLWINDOW)

            if not has_toolwindow:
                new_style = (current_style & ~WS_EX_APPWINDOW) | WS_EX_TOOLWINDOW
                set_window_exstyle(hwnd, new_style)
                user32.ShowWindow(hwnd, SW_HIDE)

            if is_window_visible(hwnd):
                user32.ShowWindow(hwnd, SW_HIDE)

            if self.taskbar_list:
                try:
                    self.taskbar_list.DeleteTab(hwnd)
                except Exception:
                    pass

    def restore_all(self):
        """모든 숨긴 창을 복원한다."""
        for hwnd in list(self.hidden.keys()):
            self.show_on_taskbar(hwnd)

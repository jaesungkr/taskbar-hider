"""Win32 API wrappers and ITaskbarList3 COM interface."""

import ctypes
import ctypes.wintypes as wintypes

import comtypes
import comtypes.client
from comtypes import GUID, HRESULT, COMMETHOD

# ──────────────────────────────────────────────
# 상수
# ──────────────────────────────────────────────
user32 = ctypes.windll.user32
ole32 = ctypes.windll.ole32

GWL_EXSTYLE = -20
WS_EX_APPWINDOW = 0x00040000
WS_EX_TOOLWINDOW = 0x00000080

SW_HIDE = 0
SW_SHOW = 5
SW_SHOWNOACTIVATE = 4

SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
SWP_NOZORDER = 0x0004

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


# ──────────────────────────────────────────────
# ITaskbarList3 COM
# ──────────────────────────────────────────────
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


# ──────────────────────────────────────────────
# 창 유틸리티
# ──────────────────────────────────────────────
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
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def get_process_name(hwnd: int) -> str:
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
    results = []

    def callback(hwnd, _lparam):
        pid = get_window_pid(hwnd)
        if pid == target_pid and is_window_visible(hwnd):
            results.append(hwnd)
        return True

    user32.EnumWindows(WNDENUMPROC(callback), 0)
    return results


def enum_taskbar_windows() -> list:
    results = []

    def callback(hwnd, _lparam):
        if not is_window_visible(hwnd):
            return True
        title = get_window_text(hwnd)
        if not title:
            return True

        ex_style = get_window_exstyle(hwnd)
        is_toolwindow = bool(ex_style & WS_EX_TOOLWINDOW)
        is_appwindow = bool(ex_style & WS_EX_APPWINDOW)

        owner = user32.GetWindow(hwnd, 4)
        if (not owner and not is_toolwindow) or is_appwindow:
            process_name = get_process_name(hwnd)
            pid = get_window_pid(hwnd)
            results.append({
                "hwnd": hwnd,
                "title": title,
                "process": process_name,
                "pid": pid,
                "ex_style": ex_style,
            })
        return True

    user32.EnumWindows(WNDENUMPROC(callback), 0)
    return results

"""Resource path resolution for both .py and .exe modes."""

import os
import sys


def get_base_dir() -> str:
    """리소스 파일의 기본 경로를 반환한다."""
    if getattr(sys, 'frozen', False):
        # PyInstaller .exe — 임시 폴더에 리소스가 풀림
        return sys._MEIPASS
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_resource_path(filename: str) -> str:
    """리소스 파일의 전체 경로를 반환한다."""
    return os.path.join(get_base_dir(), filename)

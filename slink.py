"""Slink — Hide app buttons from the Windows taskbar.

Usage:
    python slink.py
    or build with: pyinstaller Slink.spec
"""

import sys
import platform

if platform.system() != "Windows":
    print("Slink is Windows-only.")
    print("Run on Windows: python slink.py")
    print("Build:          pyinstaller Slink.spec")
    sys.exit(1)

from slink.core import SlinkCore
from slink.gui import SlinkGUI

if __name__ == "__main__":
    core = SlinkCore()
    gui = SlinkGUI(core)
    gui.run()

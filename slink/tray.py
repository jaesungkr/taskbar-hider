"""System tray icon management."""

import os
import threading


def setup_tray(on_show, on_quit, icon_path: str):
    """시스템 트레이 아이콘을 생성하고 반환한다.

    Returns:
        pystray.Icon or None
    """
    try:
        import pystray
        from PIL import Image

        if os.path.exists(icon_path):
            img = Image.open(icon_path)
        else:
            from PIL import ImageDraw
            img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.ellipse([8, 8, 56, 56], fill="#1a1a1a")

        menu = pystray.Menu(
            pystray.MenuItem("Show", on_show, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Restore All & Quit", on_quit),
        )

        icon = pystray.Icon("slink", img, "Slink", menu)
        tray_thread = threading.Thread(target=icon.run, daemon=True)
        tray_thread.start()
        return icon

    except ImportError:
        return None

"""Entry point: QApplication bootstrap."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from droiddesk.app import build_application
from droiddesk.config import Settings
from droiddesk.ui.theme import get_app_logo_icon, install_button_cursor_filter


def main() -> int:
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "droiddesk.droiddesk.app"
            )
        except Exception:
            pass

    app = QApplication(sys.argv)
    install_button_cursor_filter(app)
    app.setApplicationName("DroidDesk")
    app.setOrganizationName("DroidDesk")
    app.setWindowIcon(get_app_logo_icon())

    settings = Settings.load()
    window = build_application(settings)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

"""Entry point: QApplication bootstrap."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from droiddesk.app import build_application
from droiddesk.config import Settings


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("DroidDesk")
    app.setOrganizationName("DroidDesk")

    settings = Settings.load()
    window = build_application(settings)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

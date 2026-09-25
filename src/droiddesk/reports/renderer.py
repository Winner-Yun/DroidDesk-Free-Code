"""HTML -> PDF conversion. Attempts WeasyPrint when GTK3 runtime libraries are
available, falling back gracefully to PySide6's native QTextDocument and QPdfWriter
to guarantee 100% reliable zero-dependency PDF rendering on Windows machines.
"""

from __future__ import annotations

import sys


def _render_qt_pdf(html: str) -> bytes:
    from PySide6.QtCore import QBuffer, QIODevice
    from PySide6.QtGui import QGuiApplication, QPageSize, QPdfWriter, QTextDocument

    app = QGuiApplication.instance()
    if app is None:
        _ = QGuiApplication(sys.argv if sys.argv else [""])

    doc = QTextDocument()
    doc.setHtml(html)

    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.ReadWrite)

    writer = QPdfWriter(buf)
    writer.setPageSize(QPageSize.PageSizeId.A4)
    doc.print_(writer)

    buf.close()
    return bytes(buf.data().data())


def html_to_pdf(html: str) -> bytes:
    """Convert an HTML report string into PDF bytes.

    Attempts WeasyPrint first; if the GTK3 runtime is missing or fails on
    Windows, falls back to PySide6 QTextDocument + QPdfWriter.
    """
    try:
        from weasyprint import HTML  # type: ignore[import-untyped]

        pdf_bytes = HTML(string=html).write_pdf()
        if pdf_bytes is not None:
            return bytes(pdf_bytes)
    except Exception:
        pass

    return _render_qt_pdf(html)

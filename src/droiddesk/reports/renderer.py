"""HTML -> PDF conversion via WeasyPrint. See Section 2.2 and 10.1 — verify this in
a packaged (Nuitka) build early, since WeasyPrint's GTK dependency is known to be
awkward to bundle on Windows; ReportLab is the documented fallback.
"""

from __future__ import annotations


def html_to_pdf(html: str) -> bytes:
    """Convert an HTML report string into PDF bytes using WeasyPrint.

    Note: On Windows, WeasyPrint depends on the GTK3 runtime libraries
    (libgobject-2.0-0, etc.). If the GTK3 runtime is missing from PATH,
    an informative RuntimeError is raised.
    """
    try:
        from weasyprint import HTML  # type: ignore[import-untyped]
    except (ImportError, OSError) as exc:
        raise RuntimeError(
            "WeasyPrint failed to load. On Windows, ensure the GTK3 runtime libraries "
            "(e.g., MSYS2 or GTK3 for Windows) are installed and available in PATH."
        ) from exc

    pdf_bytes = HTML(string=html).write_pdf()
    if pdf_bytes is None:
        return b""
    return bytes(pdf_bytes)

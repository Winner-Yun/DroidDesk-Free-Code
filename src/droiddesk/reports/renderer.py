"""HTML -> PDF conversion via WeasyPrint. See Section 2.2 and 10.1 — verify this in
a packaged (Nuitka) build early, since WeasyPrint's GTK dependency is known to be
awkward to bundle on Windows; ReportLab is the documented fallback.
"""

from __future__ import annotations


def html_to_pdf(html: str) -> bytes:
    # TODO(Phase 3): from weasyprint import HTML; return HTML(string=html).write_pdf()
    raise NotImplementedError

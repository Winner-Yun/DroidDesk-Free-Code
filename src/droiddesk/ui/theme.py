"""QSS stylesheet, palette, and fonts for the application shell."""

from __future__ import annotations

STYLESHEET = """
QMainWindow {
    background: #1e1f22;
}
QListWidget#sidebar {
    background: #17181a;
    border: none;
    font-size: 13px;
}
QStatusBar {
    font-size: 12px;
}
"""

# Risk colours for the persistently-visible active-environment indicator
# (Section 6.8) — the single piece of always-visible state that prevents most of
# the mistakes the tool exists to catch.
ENVIRONMENT_RISK_COLORS = {
    "production": "#c0392b",
    "staging": "#e67e22",
    "development": "#27ae60",
}

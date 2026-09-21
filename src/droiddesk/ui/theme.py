"""QSS stylesheet, palette, and fonts for the application shell.

Colours are picked to match the approved mockups (`ui/*.png` at the repo root):
a near-black shell, a maroon active-environment bar, and the severity palette
below is shared verbatim with `widgets/severity_badge.py` and
`ENVIRONMENT_RISK_COLORS` so status colour always means the same thing
everywhere in the app (Section 1.3, "classify, do not alarm").
"""

from __future__ import annotations

# -- Palette ------------------------------------------------------------

BG_APP = "#1c1d20"
BG_SIDEBAR = "#151618"
BG_PANEL = "#212226"
BG_PANEL_ALT = "#25262b"
BG_INPUT = "#1a1b1e"
BG_HOVER = "#2a2c31"
BG_SELECTED = "#2f333c"

BORDER = "#2c2d33"
BORDER_LIGHT = "#35373e"

TEXT = "#eef0f2"
TEXT_MUTED = "#8b8e94"
TEXT_DIM = "#5c5f66"

ACCENT_RED = "#c0392b"
ACCENT_RED_BRIGHT = "#e0574a"
ACCENT_ORANGE = "#e67e22"
ACCENT_YELLOW = "#f1c40f"
ACCENT_GREEN = "#27ae60"
ACCENT_GRAY = "#7f8c8d"
ACCENT_BLUE = "#5b9bd5"

HEADER_BG_START = "#2a1418"
HEADER_BG_END = "#1c1719"
HEADER_BORDER = "#4a2226"

# Risk colours for the persistently-visible active-environment indicator
# (Section 6.8) — the single piece of always-visible state that prevents most of
# the mistakes the tool exists to catch.
ENVIRONMENT_RISK_COLORS = {
    "production": ACCENT_RED,
    "staging": ACCENT_ORANGE,
    "development": ACCENT_GREEN,
    "dev": ACCENT_GREEN,
}

# Verdict / status colours shared across Dashboard, Test runner, Release gate.
STATUS_COLORS = {
    "pass": ACCENT_GREEN,
    "warn": ACCENT_YELLOW,
    "fail": ACCENT_RED,
    "info": ACCENT_GRAY,
}

SEVERITY_COLORS = {
    "critical": ACCENT_RED,
    "high": ACCENT_ORANGE,
    "review": ACCENT_YELLOW,
    "info": ACCENT_GRAY,
}

FONT_FAMILY = "Segoe UI"
MONO_FAMILY = "Cascadia Mono"

STYLESHEET = f"""
* {{
    font-family: "{FONT_FAMILY}";
    color: {TEXT};
}}
QMainWindow, QWidget#appRoot, QWidget#bodyRow {{
    background: {BG_APP};
}}
QWidget#page {{
    background: {BG_APP};
}}
QLabel {{
    background: transparent;
}}
QLabel[role="pageTitle"] {{
    font-size: 20px;
    font-weight: 600;
}}
QLabel[role="pageSubtitle"] {{
    color: {TEXT_MUTED};
    font-size: 12px;
}}
QLabel[role="sectionTitle"] {{
    font-size: 13px;
    font-weight: 600;
}}
QLabel[role="muted"] {{
    color: {TEXT_MUTED};
    font-size: 12px;
}}
QLabel[role="dim"] {{
    color: {TEXT_DIM};
    font-size: 11px;
}}
QLabel[role="mono"] {{
    font-family: "{MONO_FAMILY}";
    color: {ACCENT_BLUE};
    font-size: 12px;
}}
QLabel[role="statNumber"] {{
    font-size: 30px;
    font-weight: 700;
}}

/* -- Brand block (top-left, above the sidebar) -------------------- */
QWidget#brandBlock {{
    background: {BG_SIDEBAR};
    border-bottom: 1px solid {BORDER};
    border-right: 1px solid {BORDER};
}}
QLabel#brandTitle {{
    font-size: 15px;
    font-weight: 700;
}}
QLabel#brandSubtitle {{
    color: {TEXT_DIM};
    font-size: 11px;
}}

/* -- Environment bar (top-right) ------------------------------------ */
QWidget#environmentBar {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {HEADER_BG_START}, stop:1 {HEADER_BG_END});
    border-bottom: 1px solid {HEADER_BORDER};
}}
QLabel#envIcon {{
    color: {ACCENT_RED_BRIGHT};
    font-size: 15px;
}}
QLabel#envLabel {{
    color: {ACCENT_RED_BRIGHT};
    font-weight: 700;
    font-size: 12px;
    letter-spacing: 1px;
}}
QLabel#envValue {{
    color: {TEXT};
    font-weight: 600;
    font-size: 13px;
}}
QLabel#envDetail {{
    color: {TEXT_MUTED};
    font-size: 12px;
}}

/* -- Sidebar --------------------------------------------------------- */
QWidget#sidebar {{
    background: {BG_SIDEBAR};
    border-right: 1px solid {BORDER};
}}
QLabel[role="navSection"] {{
    color: {TEXT_DIM};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
    padding: 10px 16px 4px 16px;
}}
QPushButton[role="navItem"] {{
    text-align: left;
    padding: 7px 14px;
    margin: 0px 8px;
    border-radius: 5px;
    border: none;
    background: transparent;
    color: {TEXT_MUTED};
    font-size: 13px;
}}
QPushButton[role="navItem"]:hover {{
    background: {BG_HOVER};
    color: {TEXT};
}}
QPushButton[role="navItem"]:checked {{
    background: {BG_SELECTED};
    color: {TEXT};
    font-weight: 600;
}}
QLabel[role="navBadge"] {{
    background: {ACCENT_RED};
    color: white;
    font-size: 10px;
    font-weight: 700;
    border-radius: 8px;
    padding: 1px 6px;
}}

/* -- Cards / panels ---------------------------------------------------*/
QFrame[role="card"] {{
    background: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QFrame[role="statCard"] {{
    background: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}

/* -- Buttons ----------------------------------------------------------*/
QPushButton {{
    background: {BG_PANEL_ALT};
    border: 1px solid {BORDER_LIGHT};
    border-radius: 5px;
    padding: 6px 14px;
    font-size: 12px;
    color: {TEXT};
}}
QPushButton:hover {{
    background: {BG_HOVER};
}}
QPushButton:pressed {{
    background: {BG_SELECTED};
}}
QPushButton:disabled {{
    color: {TEXT_DIM};
}}
QPushButton[role="primary"] {{
    background: #39424e;
    border: 1px solid #47515f;
    font-weight: 600;
}}
QPushButton[role="primary"]:hover {{
    background: #434e5c;
}}
QPushButton[role="outlineRed"] {{
    background: transparent;
    border: 1px solid {ACCENT_RED};
    color: {ACCENT_RED_BRIGHT};
    font-weight: 600;
}}
QPushButton[role="outlineRed"]:hover {{
    background: rgba(192, 57, 43, 0.12);
}}
QPushButton[role="link"] {{
    background: transparent;
    border: none;
    color: {TEXT_MUTED};
    text-align: left;
    padding: 2px;
}}
QPushButton[role="link"]:hover {{
    color: {TEXT};
}}

/* -- Inputs -------------------------------------------------------- */
QLineEdit, QComboBox {{
    background: {BG_INPUT};
    border: 1px solid {BORDER_LIGHT};
    border-radius: 5px;
    padding: 5px 8px;
    font-size: 12px;
    color: {TEXT};
}}
QLineEdit:focus, QComboBox:focus {{
    border: 1px solid {ACCENT_BLUE};
}}
QComboBox::drop-down {{
    border: none;
    width: 18px;
}}
QCheckBox {{
    font-size: 12px;
    color: {TEXT_MUTED};
}}

/* -- Tables ---------------------------------------------------------- */
QTableWidget, QTableView {{
    background: {BG_APP};
    alternate-background-color: {BG_APP};
    gridline-color: transparent;
    border: none;
    selection-background-color: {BG_SELECTED};
    selection-color: {TEXT};
    font-size: 12px;
}}
QTableWidget::item, QTableView::item {{
    padding: 6px 4px;
    border-bottom: 1px solid {BORDER};
}}
QHeaderView::section {{
    background: {BG_APP};
    color: {TEXT_DIM};
    border: none;
    border-bottom: 1px solid {BORDER_LIGHT};
    padding: 6px 4px;
    font-size: 11px;
    font-weight: 600;
    text-align: left;
}}
QTableCornerButton::section {{
    background: {BG_APP};
    border: none;
}}

/* -- Tabs -------------------------------------------------------------*/
QTabWidget::pane {{
    border: none;
    border-top: 1px solid {BORDER};
}}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_MUTED};
    padding: 8px 4px;
    margin-right: 20px;
    border-bottom: 2px solid transparent;
    font-size: 13px;
}}
QTabBar::tab:selected {{
    color: {TEXT};
    border-bottom: 2px solid {ACCENT_BLUE};
    font-weight: 600;
}}
QTabBar::tab:hover {{
    color: {TEXT};
}}

/* -- Progress bar ------------------------------------------------------*/
QProgressBar {{
    background: {BG_INPUT};
    border: 1px solid {BORDER_LIGHT};
    border-radius: 4px;
    height: 8px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background: {ACCENT_BLUE};
    border-radius: 4px;
}}

/* -- Scroll area / plain text ------------------------------------------*/
QScrollArea {{
    border: none;
    background: transparent;
}}
QPlainTextEdit {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    font-family: "{MONO_FAMILY}";
    font-size: 12px;
    color: {TEXT};
}}
QSplitter::handle {{
    background: {BORDER};
    width: 1px;
}}

/* -- Status bar ---------------------------------------------------------*/
QStatusBar {{
    background: {BG_SIDEBAR};
    border-top: 1px solid {BORDER};
    font-size: 11px;
    color: {TEXT_DIM};
}}
QStatusBar::item {{
    border: none;
}}
QLabel[role="toolChip"] {{
    color: {ACCENT_GREEN};
    font-family: "{MONO_FAMILY}";
    font-size: 11px;
    padding-right: 10px;
}}
QLabel[role="toolChipWarn"] {{
    color: {ACCENT_ORANGE};
    font-family: "{MONO_FAMILY}";
    font-size: 11px;
    padding-right: 10px;
}}
"""

"""Theme, palette, stylesheet definitions, and icon management for DroidDesk."""

from __future__ import annotations

from pathlib import Path
from typing import override

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QIcon, QPixmap
from tkinter_icons import LucideIcon  # type: ignore[import-untyped]

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

# Environment risk colors
ENVIRONMENT_RISK_COLORS = {
    "production": ACCENT_RED,
    "staging": ACCENT_ORANGE,
    "development": ACCENT_GREEN,
    "dev": ACCENT_GREEN,
}

# Verdict and status colors
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
_ICON_CACHE: dict[tuple[str, int, str, str | None], QIcon] = {}
_PIXMAP_CACHE: dict[tuple[str, int, str], QPixmap] = {}
_CURRENT_THEME: str = "dark"


def get_current_theme() -> str:
    """Return the currently active theme mode ('dark' or 'light')."""
    return _CURRENT_THEME


def set_current_theme(mode: str) -> None:
    """Set the currently active theme mode ('dark' or 'light')."""
    global _CURRENT_THEME
    _CURRENT_THEME = mode.lower()


def is_light() -> bool:
    """Check if the currently active theme is light mode."""
    return _CURRENT_THEME == "light"


def is_dark() -> bool:
    """Check if the currently active theme is dark mode."""
    return _CURRENT_THEME == "dark"


def get_pixmap(name: str, size: int = 16, color: str | None = None) -> QPixmap:
    """Render a Lucide icon by name as a QPixmap with caching.

    If color is None, defaults to theme-appropriate muted text color.
    """
    if color is None:
        color = "#6b7280" if is_light() else TEXT_MUTED

    cache_key = (name, size, color)
    if cache_key in _PIXMAP_CACHE:
        return _PIXMAP_CACHE[cache_key]

    try:
        data: bytes = LucideIcon.render_data(name, size=size, color=color)
        pix = QPixmap()
        if pix.loadFromData(data):
            _PIXMAP_CACHE[cache_key] = pix
            return pix
    except Exception:
        pass
    fallback = QPixmap(size, size)
    fallback.fill(Qt.GlobalColor.transparent)
    return fallback


def get_icon(
    name: str,
    size: int = 16,
    color: str | None = None,
    active_color: str | None = None,
) -> QIcon:
    """Render a Lucide icon by name as a QIcon.

    Supports an optional active_color for checked/selected widget states.
    If color is None, dynamically defaults to theme-appropriate muted text color.
    """
    if color is None:
        color = "#6b7280" if is_light() else TEXT_MUTED
    if active_color is None:
        active_color = "#111827" if is_light() else TEXT

    cache_key = (name, size, color, active_color)
    if cache_key in _ICON_CACHE:
        return _ICON_CACHE[cache_key]

    icon = QIcon()
    off_pix = get_pixmap(name, size=size, color=color)
    icon.addPixmap(off_pix, QIcon.Mode.Normal, QIcon.State.Off)

    if active_color:
        on_pix = get_pixmap(name, size=size, color=active_color)
        icon.addPixmap(on_pix, QIcon.Mode.Normal, QIcon.State.On)
        icon.addPixmap(on_pix, QIcon.Mode.Selected, QIcon.State.Off)
        icon.addPixmap(on_pix, QIcon.Mode.Selected, QIcon.State.On)

    _ICON_CACHE[cache_key] = icon
    return icon


RESOURCES_ICONS_DIR = Path(__file__).resolve().parent.parent / "resources" / "icons"
APP_LOGO_PNG = RESOURCES_ICONS_DIR / "logo.png"
APP_LOGO_ICO = RESOURCES_ICONS_DIR / "droiddesk.ico"

_APP_LOGO_PIXMAP_CACHE: dict[int, QPixmap] = {}
_APP_LOGO_ICON_CACHE: QIcon | None = None


def get_app_logo_pixmap(size: int = 24) -> QPixmap:
    """Return the application logo rendered as a smoothly scaled QPixmap."""
    if size in _APP_LOGO_PIXMAP_CACHE:
        return _APP_LOGO_PIXMAP_CACHE[size]

    if APP_LOGO_PNG.exists():
        src_pix = QPixmap(str(APP_LOGO_PNG))
        if not src_pix.isNull():
            scaled = src_pix.scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            _APP_LOGO_PIXMAP_CACHE[size] = scaled
            return scaled

    # Fallback to vector icon if image resource is missing
    return get_pixmap("smartphone", size=size, color=ACCENT_BLUE)


def get_app_logo_icon() -> QIcon:
    """Return the application logo as a multi-resolution QIcon."""
    global _APP_LOGO_ICON_CACHE
    if _APP_LOGO_ICON_CACHE is not None:
        return _APP_LOGO_ICON_CACHE

    if APP_LOGO_ICO.exists():
        icon = QIcon(str(APP_LOGO_ICO))
        if not icon.isNull():
            _APP_LOGO_ICON_CACHE = icon
            return icon

    if APP_LOGO_PNG.exists():
        icon = QIcon(str(APP_LOGO_PNG))
        if not icon.isNull():
            _APP_LOGO_ICON_CACHE = icon
            return icon

    # Fallback to vector icon
    return get_icon("smartphone", size=32, color=ACCENT_BLUE)

def get_stylesheet(mode: str = "dark") -> str:
    is_light = mode.lower() == "light"

    bg_app = "#f3f4f6" if is_light else BG_APP
    bg_sidebar = "#e5e7eb" if is_light else BG_SIDEBAR
    bg_panel = "#ffffff" if is_light else BG_PANEL
    bg_panel_alt = "#f9fafb" if is_light else BG_PANEL_ALT
    bg_input = "#ffffff" if is_light else BG_INPUT
    bg_hover = "#e5e7eb" if is_light else BG_HOVER
    bg_selected = "#d1d5db" if is_light else BG_SELECTED

    border = "#d1d5db" if is_light else BORDER
    border_light = "#e5e7eb" if is_light else BORDER_LIGHT

    text = "#111827" if is_light else TEXT
    text_muted = "#4b5563" if is_light else TEXT_MUTED
    text_dim = "#6b7280" if is_light else TEXT_DIM

    header_bg_start = "#fee2e2" if is_light else HEADER_BG_START
    header_bg_end = "#fef2f2" if is_light else HEADER_BG_END
    header_border = "#fecaca" if is_light else HEADER_BORDER
    bottom_sheet_bg = (
        "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #eff6ff, stop:1 #f0fdf4)"
        if is_light
        else "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1a1e27, stop:1 #1e2430)"
    )
    bottom_sheet_border = "#bfdbfe" if is_light else "#2e3a4e"

    danger_bg = "#fef2f2" if is_light else "#2a1418"
    danger_border = "#fecaca" if is_light else "#7f1d1d"
    danger_hover = "#fee2e2" if is_light else "#3b171c"

    primary_bg = "#2563eb"
    primary_hover = "#1d4ed8"
    primary_pressed = "#1e40af"
    primary_border = "#1d4ed8" if is_light else "#3b82f6"

    apk_remove_bg = "#fee2e2" if is_light else "rgba(224, 87, 74, 0.08)"
    apk_remove_border = "#fca5a5" if is_light else "rgba(224, 87, 74, 0.4)"
    apk_remove_text = "#dc2626" if is_light else "#e0574a"

    env_badge_bg = "#f3e8ff" if is_light else "rgba(167, 139, 250, 0.15)"
    env_badge_color = "#7e22ce" if is_light else "#c4b5fd"
    env_badge_border = "#d8b4fe" if is_light else "rgba(167, 139, 250, 0.35)"

    line_warn_bg = "#fef3c7" if is_light else "#3b2816"
    line_warn_color = "#b45309" if is_light else "#fbbf24"
    line_warn_border = "#fde68a" if is_light else "#78350f"

    line_neutral_bg = "#f3f4f6" if is_light else "#23252a"
    line_neutral_color = "#4b5563" if is_light else "#9ca3af"
    line_neutral_border = "#d1d5db" if is_light else "#35373e"

    rec_box_bg = "rgba(59, 130, 246, 0.07)" if is_light else "rgba(91, 155, 213, 0.08)"
    rec_box_border = "rgba(59, 130, 246, 0.25)" if is_light else "rgba(91, 155, 213, 0.25)"

    keystore_bg = "#fefce8" if is_light else "rgba(241, 196, 15, 0.1)"
    keystore_border = "#fef08a" if is_light else "rgba(241, 196, 15, 0.4)"
    keystore_title = "#ca8a04" if is_light else "#f1c40f"

    bottom_sheet_title_color = "#0284c7" if is_light else "#38bdf8"

    return f"""
* {{
    font-family: "{FONT_FAMILY}";
    color: {text};
}}
QMainWindow, QDialog, QWidget#appRoot, QWidget#bodyRow, QWidget#page, QWidget[role="page"] {{
    background: {bg_app};
}}
QLabel {{
    background: transparent;
}}
QLabel[role="pageTitle"] {{
    font-size: 20px;
    font-weight: 600;
    color: {text};
}}
QLabel[role="pageSubtitle"] {{
    color: {text_muted};
    font-size: 12px;
}}
QLabel[role="sectionTitle"] {{
    font-size: 13px;
    font-weight: 600;
    color: {text};
}}
QLabel[role="muted"] {{
    color: {text_muted};
    font-size: 12px;
}}
QLabel[role="dim"] {{
    color: {text_dim};
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
    background: {bg_sidebar};
    border-bottom: 1px solid {border};
    border-right: 1px solid {border};
}}
QLabel#brandTitle {{
    font-size: 15px;
    font-weight: 700;
}}
QLabel#brandSubtitle {{
    color: {text_dim};
    font-size: 11px;
}}

/* -- Environment bar (top-right) ------------------------------------ */
QWidget#environmentBar {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {header_bg_start}, stop:1 {header_bg_end});
    border-bottom: 1px solid {header_border};
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
    color: {text};
    font-weight: 600;
    font-size: 13px;
}}
QLabel#envDetail {{
    color: {text_muted};
    font-size: 12px;
}}

/* -- Sidebar --------------------------------------------------------- */
QWidget#sidebar {{
    background: {bg_sidebar};
    border-right: 1px solid {border};
}}
QLabel[role="navSection"] {{
    color: {text_dim};
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
    color: {text_muted};
    font-size: 13px;
}}
QPushButton[role="navItem"]:hover {{
    background: {bg_hover};
    color: {text};
}}
QPushButton[role="navItem"]:checked {{
    background: {bg_selected};
    color: {text};
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
QFrame[role="card"], QFrame[role="deviceCard"] {{
    background: {bg_panel};
    border: 1px solid {border};
    border-radius: 8px;
}}
QFrame[role="deviceCard"]:hover {{
    background: {bg_hover};
}}
QFrame[role="deviceCard"][selected="true"] {{
    border: 1px solid {ACCENT_BLUE};
}}
QFrame[role="statCard"] {{
    background: {bg_panel};
    border: 1px solid {border};
    border-radius: 8px;
}}
QFrame#emptyStateWidget {{
    background: {bg_panel};
    border: 1px solid {border};
    border-radius: 8px;
}}
QFrame#emptyStateWidget[frameless="true"] {{
    background: transparent;
    border: none;
}}

/* -- Detail & Container boxes across pages --------------------------- */
#locBox, #lineBox, #tokenBox, #recBox, #detailScroll, QFrame#pathCard {{
    background: {bg_panel};
    border: 1px solid {border};
    border-radius: 6px;
}}
#locBox QLabel, #tokenBox QLabel, #recBox QLabel, #lineBox QLabel {{
    background: transparent;
    border: none;
}}
#lineBox {{
    background: {danger_bg};
    border: 1px solid {danger_border};
    border-left: 3px solid #ef4444;
    border-radius: 4px;
}}
#recBox {{
    background: {rec_box_bg};
    border: 1px solid {rec_box_border};
    border-left: 3px solid #3b82f6;
    border-radius: 4px;
}}
QLabel#securityEnvBadge {{
    background: {env_badge_bg};
    color: {env_badge_color};
    border: 1px solid {env_badge_border};
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}}
QLabel[role="lineBadgeWarn"] {{
    background: {line_warn_bg};
    color: {line_warn_color};
    font-size: 11px;
    font-weight: 700;
    border: 1px solid {line_warn_border};
    border-radius: 4px;
    padding: 1px 8px;
}}
QLabel[role="lineBadgeNeutral"] {{
    background: {line_neutral_bg};
    color: {line_neutral_color};
    font-size: 11px;
    font-weight: 600;
    border: 1px solid {line_neutral_border};
    border-radius: 4px;
    padding: 1px 8px;
}}
QWidget[role="divider"], QFrame[role="divider"] {{
    background: {border};
}}
QFrame#keystoreBanner {{
    background: {keystore_bg};
    border: 1px solid {keystore_border};
    border-radius: 6px;
    padding: 10px;
}}
QLabel#keystoreTitle {{
    color: {keystore_title};
    font-weight: 700;
    font-size: 12px;
}}
QLabel#bottomSheetTitle {{
    color: {bottom_sheet_title_color};
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.5px;
}}

/* -- Bottom Sheet Note ------------------------------------------------*/
QFrame#bottomSheet {{
    background: {bottom_sheet_bg};
    border: 1px solid {bottom_sheet_border};
    border-radius: 8px;
}}

/* -- Buttons ----------------------------------------------------------*/
QPushButton, QToolButton, QCommandLinkButton {{
    background: {bg_panel_alt};
    border: 1px solid {border_light};
    border-radius: 5px;
    padding: 6px 14px;
    font-size: 12px;
    color: {text};
}}
QPushButton:hover, QToolButton:hover, QCommandLinkButton:hover {{
    background: {bg_hover};
    border-color: {border};
}}
QPushButton:pressed, QToolButton:pressed, QCommandLinkButton:pressed {{
    background: {bg_selected};
}}
QPushButton:checked, QToolButton:checked {{
    background: {bg_selected};
    color: {text};
    border-color: {ACCENT_BLUE};
}}
QPushButton:checked:hover, QToolButton:checked:hover {{
    background: {bg_hover};
}}
QPushButton:disabled, QToolButton:disabled, QCommandLinkButton:disabled {{
    color: {text_dim};
    border-color: {border_light};
}}
QPushButton[role="primary"] {{
    background: {primary_bg};
    border: 1px solid {primary_border};
    border-radius: 6px;
    color: #ffffff;
    font-weight: 600;
}}
QPushButton[role="primary"]:hover {{
    background: {primary_hover};
    color: #ffffff;
}}
QPushButton[role="primary"]:pressed {{
    background: {primary_pressed};
    color: #ffffff;
}}
QPushButton[role="primary"]:disabled {{
    background: {bg_selected};
    border: 1px solid {border_light};
    color: {text_dim};
}}
QPushButton[role="outlineRed"], QPushButton[role="danger"] {{
    background: {danger_bg};
    border: 1px solid {danger_border};
    border-radius: 5px;
    color: #ef4444;
    font-weight: 600;
}}
QPushButton[role="outlineRed"]:hover, QPushButton[role="danger"]:hover {{
    background: {danger_hover};
    color: #dc2626;
}}
QPushButton[role="link"] {{
    background: transparent;
    border: none;
    color: {text_muted};
    text-align: left;
    padding: 3px 8px;
    border-radius: 4px;
}}
QPushButton[role="link"]:hover {{
    background: {bg_hover};
    color: {text};
}}
QPushButton[role="secondary"] {{
    background: {bg_panel_alt};
    border: 1px solid {border_light};
    border-radius: 5px;
    padding: 6px 14px;
    font-size: 12px;
    color: {text};
}}
QPushButton[role="secondary"]:hover {{
    background: {bg_hover};
}}
QPushButton[role="secondary"]:pressed {{
    background: {bg_selected};
}}
QPushButton[role="tableActionDanger"] {{
    background: {danger_bg};
    border: 1px solid {danger_border};
    border-radius: 4px;
    color: #ef4444;
    font-weight: 600;
    padding: 3px 8px;
    font-size: 11px;
}}
QPushButton[role="tableActionDanger"]:hover {{
    background: {danger_hover};
    color: #dc2626;
}}
QPushButton[role="tableAction"] {{
    background: {bg_panel_alt};
    border: 1px solid {border_light};
    border-radius: 4px;
    color: {text};
    padding: 3px 8px;
    font-size: 11px;
}}
QPushButton[role="tableAction"]:hover {{
    background: {bg_hover};
}}

/* -- Appbar APK remove button ----------------------------------------- */
QPushButton#apkRemoveButton {{
    background-color: {apk_remove_bg};
    border: 1px solid {apk_remove_border};
    border-radius: 5px;
    color: {apk_remove_text};
    font-size: 12px;
    font-weight: 600;
    padding: 5px 12px;
}}
QPushButton#apkRemoveButton:hover {{
    background-color: #ef4444;
    border-color: #ef4444;
    color: #ffffff;
}}
QPushButton#apkRemoveButton:disabled {{
    background-color: transparent;
    border-color: {border_light};
    color: {text_dim};
}}

/* -- Tag Pill -------------------------------------------------------- */
QLabel[role="tagPill"] {{
    background: transparent;
    color: {text_muted};
    border: 1px solid {border_light};
    border-radius: 3px;
    padding: 1px 7px;
    font-size: 10px;
}}

/* -- Inputs -------------------------------------------------------- */
QLineEdit, QComboBox, QPlainTextEdit, QTextEdit {{
    background: {bg_input};
    border: 1px solid {border_light};
    border-radius: 5px;
    padding: 5px 8px;
    font-size: 12px;
    color: {text};
}}
QLineEdit:focus, QComboBox:focus {{
    border: 1px solid {ACCENT_BLUE};
}}
QLineEdit:read-only {{
    background: {bg_hover};
    color: {text_muted};
}}
QLineEdit#findingPathEdit {{
    background: {bg_input};
    border: 1px solid {border};
    border-radius: 4px;
    color: {ACCENT_BLUE};
    font-family: "{MONO_FAMILY}";
    font-size: 11px;
    padding: 4px 8px;
}}
QLineEdit#findingPathEdit:focus {{
    border-color: {ACCENT_BLUE};
}}
QComboBox::drop-down {{
    border: none;
    width: 18px;
}}
QCheckBox {{
    font-size: 12px;
    color: {text_muted};
}}

/* -- Tables ---------------------------------------------------------- */
QTableWidget, QTableView {{
    background: {bg_panel};
    alternate-background-color: {bg_panel};
    gridline-color: transparent;
    border: 1px solid {border};
    border-radius: 6px;
    selection-background-color: {bg_selected};
    selection-color: {text};
    font-size: 12px;
}}
QTableWidget::item, QTableView::item {{
    padding: 6px 4px;
    border-bottom: 1px solid {border_light};
    color: {text};
}}
QHeaderView::section {{
    background: {bg_panel_alt};
    color: {text_dim};
    border: none;
    border-bottom: 1px solid {border_light};
    padding: 6px 6px;
    font-size: 11px;
    font-weight: 600;
    text-align: left;
}}
QTableCornerButton::section {{
    background: {bg_panel_alt};
    border: none;
}}

/* -- Lists ----------------------------------------------------------- */
QListWidget, QListView {{
    background: {bg_panel};
    border: 1px solid {border};
    border-radius: 6px;
    color: {text};
    outline: none;
}}
QListWidget::item, QListView::item {{
    background: transparent;
    border-bottom: 1px solid {border_light};
    color: {text};
}}
QListWidget::item:hover, QListView::item:hover {{
    background: {bg_hover};
}}
QListWidget::item:selected, QListView::item:selected {{
    background: {bg_selected};
    color: {text};
}}

/* -- Tabs -------------------------------------------------------------*/
QTabWidget {{
    background: transparent;
}}
QTabWidget::pane {{
    border: none;
    border-top: 1px solid {border};
    background: transparent;
}}
QTabWidget > QStackedWidget, QTabWidget > QWidget {{
    background: transparent;
}}
QTabBar {{
    background: transparent;
}}
QTabBar::tab {{
    background: transparent;
    color: {text_muted};
    padding: 8px 12px;
    margin-right: 12px;
    border-bottom: 2px solid transparent;
    font-size: 13px;
}}
QTabBar::tab:selected {{
    color: {text};
    border-bottom: 2px solid {ACCENT_BLUE};
    font-weight: 600;
}}
QTabBar::tab:hover {{
    color: {text};
    background: {bg_hover};
    border-radius: 4px 4px 0 0;
}}

/* -- Progress bar ------------------------------------------------------*/
QProgressBar {{
    background: {bg_input};
    border: 1px solid {border_light};
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
QScrollArea, QScrollArea > QWidget, QScrollArea > QWidget > QWidget {{
    border: none;
    background: transparent;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 2px 2px 2px 0px;
}}
QScrollBar::handle:vertical {{
    background: {border_light};
    min-height: 24px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical:hover {{
    background: {text_dim};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
    background: transparent;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 0px 2px 2px 2px;
}}
QScrollBar::handle:horizontal {{
    background: {border_light};
    min-width: 24px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {text_dim};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
    background: transparent;
}}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: transparent;
}}
QPlainTextEdit {{
    background: {bg_input};
    border: 1px solid {border};
    border-radius: 6px;
    font-family: "{MONO_FAMILY}";
    font-size: 12px;
    color: {text};
}}
QSplitter::handle {{
    background: {border};
    width: 1px;
}}

/* -- Status bar ---------------------------------------------------------*/
QStatusBar {{
    background: {bg_sidebar};
    border-top: 1px solid {border};
    font-size: 11px;
    color: {text_dim};
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


def apply_theme(mode: str = "dark", widget: object | None = None) -> None:
    """Apply the stylesheet for dark or light mode to the active QApplication and all
    top-level windows.
    """
    global _CURRENT_THEME
    _CURRENT_THEME = mode.lower()
    from PySide6.QtWidgets import QApplication, QWidget

    _ICON_CACHE.clear()
    _PIXMAP_CACHE.clear()

    css = get_stylesheet(mode)
    app = QApplication.instance()
    applied_windows: set[object] = set()
    if app:
        install_button_cursor_filter(app)
        app.setStyleSheet(css)
        for top in app.topLevelWidgets():
            applied_windows.add(top)
            if hasattr(top, "set_theme"):
                top.set_theme(mode)
            else:
                top.setStyleSheet(css)
    if isinstance(widget, QWidget):
        win = widget.window()
        if win and win not in applied_windows:
            if hasattr(win, "set_theme"):
                win.set_theme(mode)
            else:
                win.setStyleSheet(css)



class ClickableCursorFilter(QObject):
    """Global event filter ensuring all clickable controls (buttons, tool buttons,
    tab bars, etc.) display a pointing hand cursor when enabled, and revert to
    standard arrow cursor when disabled.
    """

    @override
    def eventFilter(self, obj: object, event: QEvent) -> bool:
        t = event.type()
        if t in (
            QEvent.Type.Enter,
            QEvent.Type.Show,
            QEvent.Type.EnabledChange,
            QEvent.Type.Polish,
            QEvent.Type.HoverEnter,
        ):
            from PySide6.QtWidgets import QAbstractButton, QTabBar

            if isinstance(obj, (QAbstractButton, QTabBar)):
                if obj.isEnabled():
                    if obj.cursor().shape() != Qt.CursorShape.PointingHandCursor:
                        obj.setCursor(Qt.CursorShape.PointingHandCursor)
                else:
                    if obj.cursor().shape() == Qt.CursorShape.PointingHandCursor:
                        obj.setCursor(Qt.CursorShape.ArrowCursor)
        return super().eventFilter(obj, event)


_BUTTON_CURSOR_FILTER: ClickableCursorFilter | None = None


def install_button_cursor_filter(app: object | None = None) -> None:
    """Install the global clickable cursor event filter on the active QApplication."""
    global _BUTTON_CURSOR_FILTER
    from PySide6.QtWidgets import QApplication

    if app is None:
        app = QApplication.instance()
    if isinstance(app, QApplication) and _BUTTON_CURSOR_FILTER is None:
        _BUTTON_CURSOR_FILTER = ClickableCursorFilter(app)
        app.installEventFilter(_BUTTON_CURSOR_FILTER)


STYLESHEET = get_stylesheet("dark")

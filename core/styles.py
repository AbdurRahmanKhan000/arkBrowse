"""Styling, QSS stylesheet building, and SVG icons for arkBrowse."""

from __future__ import annotations

import sys
from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from .config import INCOGNITO_ACCENT

_ICON_PATHS: dict[str, str] = {
    "back": (
        '<path d="M15 6l-6 6 6 6" stroke="{c}" stroke-width="2" fill="none" '
        'stroke-linecap="round" stroke-linejoin="round"/>'
    ),
    "forward": (
        '<path d="M9 6l6 6-6 6" stroke="{c}" stroke-width="2" fill="none" '
        'stroke-linecap="round" stroke-linejoin="round"/>'
    ),
    "reload": (
        '<path d="M21 12a9 9 0 1 1-3-6.7" stroke="{c}" stroke-width="2" fill="none" '
        'stroke-linecap="round"/>'
        '<path d="M21 3v6h-6" stroke="{c}" stroke-width="2" fill="none" '
        'stroke-linecap="round" stroke-linejoin="round"/>'
    ),
    "stop": (
        '<path d="M6 6l12 12M18 6l-12 12" stroke="{c}" stroke-width="2" fill="none" '
        'stroke-linecap="round"/>'
    ),
    "home": (
        '<path d="M4 11l8-7 8 7" stroke="{c}" stroke-width="2" fill="none" '
        'stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M6 10v9h12v-9" stroke="{c}" stroke-width="2" fill="none" '
        'stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M10 19v-5h4v5" stroke="{c}" stroke-width="2" fill="none" '
        'stroke-linecap="round" stroke-linejoin="round"/>'
    ),
    "lock_closed": (
        '<rect x="5" y="11" width="14" height="9" rx="2" stroke="{c}" stroke-width="2" fill="none"/>'
        '<path d="M8 11V7a4 4 0 0 1 8 0v4" stroke="{c}" stroke-width="2" fill="none" '
        'stroke-linecap="round"/>'
    ),
    "lock_open": (
        '<rect x="5" y="11" width="14" height="9" rx="2" stroke="{c}" stroke-width="2" fill="none"/>'
        '<path d="M8 11V7a4 4 0 0 1 7.5-2" stroke="{c}" stroke-width="2" fill="none" '
        'stroke-linecap="round"/>'
    ),
    "settings": (
        '<circle cx="12" cy="12" r="3" stroke="{c}" stroke-width="2" fill="none"/>'
        '<path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1'
        'M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1" '
        'stroke="{c}" stroke-width="2" fill="none" stroke-linecap="round"/>'
    ),
    "incognito": (
        '<path d="M2 8h4l2 2h8l2-2h4" stroke="{c}" stroke-width="2" fill="none" '
        'stroke-linecap="round" stroke-linejoin="round"/>'
        '<circle cx="7" cy="13" r="3" stroke="{c}" stroke-width="2" fill="none"/>'
        '<circle cx="17" cy="13" r="3" stroke="{c}" stroke-width="2" fill="none"/>'
        '<path d="M10 13h4" stroke="{c}" stroke-width="2" fill="none"/>'
    ),
    "window": (
        '<rect x="3" y="4" width="18" height="16" rx="2" stroke="{c}" '
        'stroke-width="2" fill="none"/>'
        '<path d="M3 9h18M8 4v5M16 4v5" stroke="{c}" stroke-width="2" '
        'fill="none" stroke-linecap="round"/>'
    ),
    "save": (
        '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" '
        'stroke="{c}" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
        '<polyline points="17 21 17 13 7 13 7 21" stroke="{c}" stroke-width="2" fill="none"/>'
        '<polyline points="7 3 7 8 15 8" stroke="{c}" stroke-width="2" fill="none"/>'
    ),
    "print": (
        '<polyline points="6 9 6 2 18 2 18 9" stroke="{c}" stroke-width="2" fill="none"/>'
        '<path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2" '
        'stroke="{c}" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
        '<rect x="6" y="14" width="12" height="8" stroke="{c}" stroke-width="2" fill="none"/>'
    ),
    "image": (
        '<rect x="3" y="3" width="18" height="18" rx="2" stroke="{c}" stroke-width="2" fill="none"/>'
        '<circle cx="8.5" cy="8.5" r="1.5" fill="{c}"/>'
        '<polyline points="21 15 16 10 5 21" stroke="{c}" stroke-width="2" fill="none"/>'
    ),
    "copy": (
        '<rect x="9" y="9" width="13" height="13" rx="2" stroke="{c}" stroke-width="2" fill="none"/>'
        '<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" stroke="{c}" stroke-width="2" fill="none"/>'
    ),
    "link": (
        '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" stroke="{c}" stroke-width="2" fill="none" stroke-linecap="round"/>'
        '<path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" stroke="{c}" stroke-width="2" fill="none" stroke-linecap="round"/>'
    ),
}


def make_svg_icon(icon_name: str, color: str, size: int = 22) -> QIcon:
    """Render an SVG icon with the given color."""
    if icon_name not in _ICON_PATHS:
        return QIcon()
    inner = _ICON_PATHS[icon_name].format(c=color)
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{inner}</svg>'
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


def apply_windows_titlebar_theme(window, dark: bool) -> None:
    """Apply native dark/light theme to Windows title bar using DWM."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        hwnd = int(window.winId())
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        value = ctypes.c_int(1 if dark else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(value), ctypes.sizeof(value)
        )
    except Exception as exc:
        print(f"[arkBrowse] Could not set native title bar theme ({exc}); continuing with the default title bar.")


def build_stylesheet(palette: dict, incognito: bool = False) -> str:
    """Turn a flat color palette into a full QSS stylesheet string."""
    accent = INCOGNITO_ACCENT if incognito else palette["accent"]
    accent_hover = accent if incognito else palette["accent_hover"]

    return f"""
    QMainWindow, QDialog {{
        background-color: {palette['bg']};
        color: {palette['text']};
    }}

    QWidget {{
        color: {palette['text']};
        font-family: "Segoe UI", "Inter", "Helvetica Neue", Arial, sans-serif;
        font-size: 10.5pt;
    }}

    /* ---- Toolbar / navigation header ---- */
    QToolBar {{
        background-color: {palette['panel']};
        border: none;
        border-bottom: 1px solid {palette['border']};
        padding: 6px 8px;
        spacing: 6px;
    }}
    QToolBar QToolButton {{
        background-color: transparent;
        border: none;
        border-radius: 8px;
        padding: 6px 8px;
        color: {palette['text']};
    }}
    QToolBar QToolButton:hover {{
        background-color: {palette['elevated']};
    }}
    QToolBar QToolButton:pressed {{
        background-color: {accent};
        color: {palette['accent_text']};
    }}

    QLabel#LogoLabel {{
        padding: 0 10px 0 2px;
    }}
    QLabel#SecurityIcon {{
        padding: 0 4px;
        font-size: 12pt;
    }}
    QLabel#IncognitoBadge {{
        color: {accent};
        font-weight: 600;
        padding: 0 8px;
    }}

    /* ---- Omnibox ---- */
    QLineEdit#Omnibox {{
        background-color: {palette['elevated']};
        border: 1px solid {palette['border']};
        border-radius: 10px;
        padding: 7px 12px;
        color: {palette['text']};
        selection-background-color: {accent};
        selection-color: {palette['accent_text']};
    }}
    QLineEdit#Omnibox:focus {{
        border: 1px solid {accent};
    }}

    /* ---- Context Menu ---- */
    QMenu {{
        background-color: {palette['panel']};
        color: {palette['text']};
        border: 1px solid {palette['border']};
        border-radius: 8px;
        padding: 6px 4px;
    }}
    QMenu::item {{
        background-color: transparent;
        padding: 6px 28px 6px 12px;
        border-radius: 5px;
        margin: 1px 4px;
        font-size: 10pt;
    }}
    QMenu::item:selected {{
        background-color: {palette['elevated']};
        color: {palette['text']};
    }}
    QMenu::item:disabled {{
        color: {palette['text_dim']};
    }}
    QMenu::separator {{
        height: 1px;
        background-color: {palette['border']};
        margin: 4px 8px;
    }}

    /* ---- Generic buttons (settings dialog etc.) ---- */
    QPushButton {{
        background-color: {palette['elevated']};
        border: 1px solid {palette['border']};
        border-radius: 8px;
        padding: 7px 14px;
        color: {palette['text']};
    }}
    QPushButton:hover {{
        border: 1px solid {accent};
    }}
    QPushButton:pressed {{
        background-color: {accent};
        color: {palette['accent_text']};
    }}
    QPushButton#PrimaryButton {{
        background-color: {accent};
        color: {palette['accent_text']};
        border: none;
        font-weight: 600;
    }}
    QPushButton#PrimaryButton:hover {{
        background-color: {accent_hover};
    }}

    /* ---- Tabs ---- */
    QTabWidget::pane {{
        border: none;
        background-color: {palette['bg']};
    }}
    QTabBar {{
        background-color: {palette['panel']};
    }}
    QTabBar::tab {{
        background-color: {palette['panel']};
        color: {palette['text_dim']};
        border: none;
        border-right: 1px solid {palette['border']};
        padding: 8px 16px;
        min-width: 120px;
        max-width: 220px;
    }}
    QTabBar::tab:selected {{
        background-color: {palette['bg']};
        color: {palette['text']};
        border-bottom: 2px solid {accent};
    }}
    QTabBar::tab:hover:!selected {{
        background-color: {palette['elevated']};
        color: {palette['text']};
    }}
    QTabBar::close-button {{
        subcontrol-position: right;
        padding: 2px;
    }}

    /* ---- Forms (settings dialog) ---- */
    QComboBox, QLineEdit {{
        background-color: {palette['elevated']};
        border: 1px solid {palette['border']};
        border-radius: 6px;
        padding: 5px 8px;
        color: {palette['text']};
    }}
    QComboBox QAbstractItemView {{
        background-color: {palette['elevated']};
        color: {palette['text']};
        selection-background-color: {accent};
        selection-color: {palette['accent_text']};
        outline: none;
    }}
    QCheckBox {{
        spacing: 8px;
        padding: 4px 0;
    }}
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border-radius: 4px;
        border: 1px solid {palette['border']};
        background-color: {palette['elevated']};
    }}
    QCheckBox::indicator:checked {{
        background-color: {accent};
        border: 1px solid {accent};
    }}
    QLabel#SectionTitle {{
        font-weight: 600;
        font-size: 11.5pt;
        padding-top: 6px;
    }}
    QLabel#HintLabel {{
        color: {palette['text_dim']};
        font-size: 9pt;
        padding: 4px 0;
    }}

    QScrollBar:vertical {{
        background: {palette['panel']};
        width: 10px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {palette['elevated']};
        border-radius: 5px;
        min-height: 24px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {accent};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    """

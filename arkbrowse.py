#!/usr/bin/env python3
"""
arkBrowse — Fast, Secure, Obsidian-Dark Web Browsing.

A modern, security-focused desktop web browser built with PyQt6 and
QtWebEngine (Chromium). Single-file application: settings persist to a
local settings.json (no database), theming is done with in-memory QSS
stylesheets, and ad/tracker blocking + HTTPS upgrade are implemented via
a custom QWebEngineUrlRequestInterceptor.

Run with:  python arkbrowse.py
Requires:  PyQt6, PyQt6-WebEngine  (pip install PyQt6 PyQt6-WebEngine)

Author: Generated for the arkBrowse project.
"""

from __future__ import annotations

import base64
import ipaddress
import json
import os
import re
import sys
import tempfile
from urllib.parse import quote_plus

from PyQt6.QtCore import (
    QByteArray,
    QCoreApplication,
    QEvent,
    QSize,
    Qt,
    QTimer,
    QUrl,
    QUrlQuery,
)
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineSettings,
    QWebEngineUrlRequestInterceptor,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

APP_NAME = "arkBrowse"
APP_VERSION = "1.1.0"
ORG_NAME = "arkBrowse"
SETTINGS_VERSION = 2

# Internal sentinel URL for arkBrowse's own New Tab / start page — never
# actually sent over the network. Used as: (a) the default homepage_url,
# (b) what a blank Ctrl+T tab loads, (c) what typing it into the omnibox
# returns you to.
NEW_TAB_URL = "arkbrowse://newtab"


# ---------------------------------------------------------------------------
# Path helpers — must work both as a plain script AND as a PyInstaller build.
# ---------------------------------------------------------------------------

def resource_path(relative_path: str) -> str:
    """Resolve a bundled resource (e.g. logo.png) whether running from
    source or from a PyInstaller onefile/onedir executable."""
    base_path = getattr(sys, "_MEIPASS", os.path.abspath(os.path.dirname(__file__)))
    return os.path.join(base_path, relative_path)


def settings_file_path() -> str:
    """Return a per-user preferences path, not an installation path.

    The old build wrote beside the executable, which fails for read-only
    installs and makes a portable bundle accidentally share preferences with
    every user of the folder.  This file contains only UI preferences; the
    browser profile itself is intentionally ephemeral and never stored here.
    """
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
        if not base:
            base = os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
    elif sys.platform == "darwin":
        base = os.path.join(
            os.path.expanduser("~"), "Library", "Application Support"
        )
    else:
        base = os.environ.get(
            "XDG_CONFIG_HOME", os.path.join(os.path.expanduser("~"), ".config")
        )
    return os.path.join(base, APP_NAME, "settings.json")


def apply_windows_titlebar_theme(window, dark: bool) -> None:
    """Ask Windows to draw this window's *native* title bar in dark mode.

    Qt's stylesheets only ever reach the content area inside a window — the
    title bar (the strip with the icon, window title, and minimize/
    maximize/close buttons) is drawn by the OS window manager and is
    completely outside QSS's reach. On Windows 10 (version 2004/20H1 and
    later) and Windows 11, the only way to theme it is this DWM call.

    This is a Windows-only feature, silently skipped everywhere else
    (macOS/Linux window managers have their own separate theming
    mechanisms, out of scope here). Also silently skipped, rather than
    raising, on older Windows builds that don't support the attribute —
    the app should never fail to start just because the title bar can't
    be recolored.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        hwnd = int(window.winId())
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20  # Windows 10 20H1+ / Windows 11
        value = ctypes.c_int(1 if dark else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(value), ctypes.sizeof(value)
        )
    except Exception as exc:  # pragma: no cover - platform/OS-version dependent
        print(f"[arkBrowse] Could not set native title bar theme ({exc}); continuing with the default title bar.")


# ---------------------------------------------------------------------------
# Settings persistence (plain JSON file — no database, per spec).
# ---------------------------------------------------------------------------

DEFAULT_SETTINGS = {
    "theme_name": "Obsidian Dark",
    "homepage_url": NEW_TAB_URL,
    "default_search_engine": "Google",
    "adblock_enabled": True,
    "force_https_enabled": True,
    "javascript_enabled": True,
    "autoplay_requires_user_gesture": True,
}

SEARCH_ENGINES = {
    "Google": "https://www.google.com/search?q=",
    "DuckDuckGo": "https://duckduckgo.com/?q=",
    "Bing": "https://www.bing.com/search?q=",
    "Startpage": "https://www.startpage.com/sp/search?query=",
    "Brave Search": "https://search.brave.com/search?q=",
    "arkEngine": "http://127.0.0.1:8000/search?q=",
}


class SettingsManager:
    """Loads/saves a flat dict of user preferences to settings.json.

    Any read/parse failure falls back to DEFAULT_SETTINGS instead of
    crashing the app — a corrupted or hand-edited settings.json should
    never prevent arkBrowse from starting.
    """

    def __init__(self, path: str | None = None):
        self._explicit_path = path is not None
        self.path = path or settings_file_path()
        self.data: dict = dict(DEFAULT_SETTINGS)
        self.load()

    def load(self) -> None:
        source_path = self.path
        if not os.path.exists(source_path) and not self._explicit_path:
            # Migrate the old portable settings.json location on first run.
            # Only preferences move; browsing data is never read or migrated.
            legacy_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "settings.json"
            )
            if legacy_path != self.path and os.path.exists(legacy_path):
                source_path = legacy_path
        if not os.path.exists(source_path):
            return
        try:
            with open(source_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                for key, default_value in DEFAULT_SETTINGS.items():
                    value = loaded.get(key, default_value)
                    if self._valid_value(key, value):
                        self.data[key] = value
                if source_path != self.path:
                    self.save()
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
            print(f"[arkBrowse] settings.json could not be read ({exc}); using defaults.")
            self.data = dict(DEFAULT_SETTINGS)

    def save(self) -> None:
        try:
            directory = os.path.dirname(os.path.abspath(self.path))
            os.makedirs(directory, exist_ok=True)
            fd, temporary_path = tempfile.mkstemp(
                prefix=".arkbrowse-settings-", suffix=".tmp", dir=directory
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(
                        {"settings_version": SETTINGS_VERSION, **self.data},
                        f,
                        indent=2,
                    )
                    f.write("\n")
                    f.flush()
                    os.fsync(f.fileno())
                if os.name != "nt":
                    os.chmod(temporary_path, 0o600)
                os.replace(temporary_path, self.path)
            finally:
                if os.path.exists(temporary_path):
                    os.unlink(temporary_path)
        except OSError as exc:
            print(f"[arkBrowse] settings.json could not be written ({exc}).")

    def get(self, key: str):
        return self.data.get(key, DEFAULT_SETTINGS.get(key))

    def set(self, key: str, value) -> None:
        if key in DEFAULT_SETTINGS and self._valid_value(key, value):
            self.data[key] = value

    @staticmethod
    def _valid_value(key: str, value) -> bool:
        if key in {
            "adblock_enabled",
            "force_https_enabled",
            "javascript_enabled",
            "autoplay_requires_user_gesture",
        }:
            return isinstance(value, bool)
        if key == "theme_name":
            return isinstance(value, str) and value in THEME_PALETTES
        if key == "default_search_engine":
            return isinstance(value, str) and value in SEARCH_ENGINES
        if key == "homepage_url":
            return isinstance(value, str) and len(value) <= 4096
        return True


# ---------------------------------------------------------------------------
# Themes — each is a flat palette turned into a QSS stylesheet string.
# ---------------------------------------------------------------------------

THEME_PALETTES = {
    "Obsidian Dark": {
        "bg": "#0D0D0D",
        "panel": "#161618",
        "elevated": "#222225",
        "border": "#2C2C30",
        "text": "#E8E8EA",
        "text_dim": "#9A9AA2",
        "accent": "#00E5FF",
        "accent_hover": "#33ECFF",
        "accent_text": "#0D0D0D",
        "danger": "#FF5C5C",
    },
    "Dark Slate": {
        "bg": "#12161C",
        "panel": "#1B212B",
        "elevated": "#262E3A",
        "border": "#333D4C",
        "text": "#E4E9F0",
        "text_dim": "#8FA0B3",
        "accent": "#3B82F6",
        "accent_hover": "#5C96F8",
        "accent_text": "#0B0F14",
        "danger": "#F87171",
    },
    "Cyberpunk Neon": {
        "bg": "#08060C",
        "panel": "#140B1F",
        "elevated": "#1F1330",
        "border": "#3A2050",
        "text": "#F2E9FF",
        "text_dim": "#B08FE0",
        "accent": "#FF2E9F",
        "accent_hover": "#FF5CB6",
        "accent_text": "#08060C",
        "danger": "#FF4D4D",
    },
    "Classic Light": {
        "bg": "#F5F6F8",
        "panel": "#FFFFFF",
        "elevated": "#ECEEF1",
        "border": "#D7DBE0",
        "text": "#1A1D21",
        "text_dim": "#5B6270",
        "accent": "#2563EB",
        "accent_hover": "#3B76F0",
        "accent_text": "#FFFFFF",
        "danger": "#DC2626",
    },
}

INCOGNITO_ACCENT = "#7C3AED"  # violet accent used to visually mark private windows


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


# ---------------------------------------------------------------------------
# Toolbar icons — hand-drawn, minimal line-style SVGs rendered to QIcon at
# runtime, colored to match the active theme. Replaces plain emoji
# characters (which render inconsistently across OSes/fonts and look
# unprofessional in a toolbar) with a single consistent icon set that stays
# in sync with whichever theme is active.
# ---------------------------------------------------------------------------

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
}


def make_svg_icon(icon_name: str, color: str, size: int = 22) -> QIcon:
    """Render one of _ICON_PATHS as a QIcon in the given color. Rendering
    happens at call time (not pre-baked into files) specifically so icons
    can be recolored on every theme switch, the same way build_stylesheet()
    and build_start_page_html() are regenerated per theme."""
    inner = _ICON_PATHS[icon_name].format(c=color)
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{inner}</svg>'
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


# ---------------------------------------------------------------------------
# Ad / tracker blocking + forced HTTPS upgrade.
# ---------------------------------------------------------------------------

# Fallback list used only if the bundled filter file is missing. The normal
# source is filters.txt, which is parsed as a lightweight host-oriented
# Adblock list and can be updated without changing Python code.
FALLBACK_BLOCKED_DOMAINS = [
    "doubleclick.net",
    "googlesyndication.com",
    "googleadservices.com",
    "google-analytics.com",
    "googletagmanager.com",
    "googletagservices.com",
    "adservice.google.com",
    "adnxs.com",
    "adsystem.com",
    "amazon-adsystem.com",
    "connect.facebook.net",
    "facebook.net",
    "scorecardresearch.com",
    "quantserve.com",
    "outbrain.com",
    "taboola.com",
    "criteo.com",
    "criteo.net",
    "moatads.com",
    "adform.net",
    "pubmatic.com",
    "rubiconproject.com",
    "openx.net",
    "casalemedia.com",
    "yieldmo.com",
    "media.net",
    "advertising.com",
    "adroll.com",
    "bluekai.com",
    "mathtag.com",
    "serving-sys.com",
    "2mdn.net",
    "adsafeprotected.com",
    "hotjar.com",
    "mixpanel.com",
    "segment.io",
]


def parse_filter_list(path: str) -> set[str]:
    """Read host rules from a bundled Adblock/hosts-style filter file.

    Network filtering runs for every request, so this deliberately compiles
    only domain rules. Cosmetic rules, regex rules, allowlists, and resource
    modifiers are ignored rather than guessed at.
    """
    domains: set[str] = set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith(("#", "!")) or line.startswith("@@"):
                    continue
                if line.startswith("||"):
                    line = line[2:].split("^", 1)[0].split("$", 1)[0]
                elif line.startswith(("0.0.0.0 ", "127.0.0.1 ")):
                    line = line.split(None, 1)[1].split("#", 1)[0].strip()
                if "/" in line or "*" in line or ":" in line:
                    continue
                line = line.rstrip(".").lower()
                if re.fullmatch(
                    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}",
                    line,
                ):
                    domains.add(line)
    except (OSError, UnicodeDecodeError):
        return set()
    return domains


_FILTER_DOMAINS_CACHE: set[str] | None = None


def load_blocked_domains() -> set[str]:
    global _FILTER_DOMAINS_CACHE
    if _FILTER_DOMAINS_CACHE is None:
        loaded = parse_filter_list(resource_path("filters.txt"))
        _FILTER_DOMAINS_CACHE = loaded or set(FALLBACK_BLOCKED_DOMAINS)
    return _FILTER_DOMAINS_CACHE


class BrowserSessionPolicy:
    """In-memory privacy policy shared by normal windows in one app session."""

    def __init__(self):
        self.http_exceptions: set[str] = set()

    @staticmethod
    def _key(url: QUrl) -> str:
        host = url.host().lower().rstrip(".")
        port = url.port()
        return f"{host}:{port}" if port != -1 else host

    def allows_http(self, url: QUrl) -> bool:
        return self._key(url) in self.http_exceptions

    def allow_http(self, url: QUrl) -> None:
        self.http_exceptions.add(self._key(url))


class AdBlockInterceptor(QWebEngineUrlRequestInterceptor):
    """Blocks requests to known ad/tracker domains and upgrades http:// to
    https:// when enabled. Reads its two on/off flags live from the shared
    SettingsManager, so toggling either setting takes effect immediately —
    no need to recreate the interceptor or restart the app.
    """

    def __init__(
        self,
        settings_manager: SettingsManager,
        session_policy: BrowserSessionPolicy | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.session_policy = session_policy or BrowserSessionPolicy()
        self._blocked_set = load_blocked_domains()

    def _is_blocked_host(self, host: str) -> bool:
        host = host.lower().rstrip(".")
        while host:
            if host in self._blocked_set:
                return True
            if "." not in host:
                break
            host = host.split(".", 1)[1]
        return False

    @staticmethod
    def _is_local_host(host: str) -> bool:
        """True for loopback / same-machine hosts and addresses. Forcing
        HTTPS on these makes no sense — a local dev server
        like arkEngine (http://127.0.0.1:8000) has no TLS certificate, so
        upgrading the scheme would just break the connection outright
        rather than make it more secure."""
        host = host.lower()
        if host in ("localhost", "0.0.0.0") or host.endswith(".localhost"):
            return True
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False

    @staticmethod
    def _is_main_frame(info) -> bool:
        try:
            resource_type = info.resourceType()
            # PyQt's enum is not int-convertible in current Qt versions.
            # The enum name is stable across supported PyQt6 releases.
            return getattr(resource_type, "name", "") == "ResourceTypeMainFrame"
        except Exception:
            # Fail closed: an unknown request type must not silently redirect
            # subresources as if they were top-level navigation.
            return False

    def interceptRequest(self, info) -> None:  # noqa: N802 (Qt override name)
        # This runs on QtWebEngine's I/O thread. Keep it fast and never let
        # an unexpected exception escape — that would take Chromium's
        # network thread down with it.
        try:
            url = info.requestUrl()
            host = url.host()

            if self.settings_manager.get("adblock_enabled") and host and self._is_blocked_host(host):
                info.block(True)
                return

            if (
                self.settings_manager.get("force_https_enabled")
                and url.scheme() == "http"
                and not self._is_local_host(host)
                and self._is_main_frame(info)
                and not self.session_policy.allows_http(url)
            ):
                upgraded = QUrl(url)
                upgraded.setScheme("https")
                info.redirect(upgraded)
        except Exception as exc:  # pragma: no cover - defensive guard
            print(f"[arkBrowse] AdBlockInterceptor error: {exc}")


# ---------------------------------------------------------------------------
# Omnibox: URL-vs-search detection.
# ---------------------------------------------------------------------------

_HOSTNAME_RE = re.compile(
    r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+"
    r"(?:[a-zA-Z]{2,63}|local)(?::[0-9]{1,5})?(?:[/?#].*)?$",
    re.IGNORECASE,
)
_LOCALHOST_RE = re.compile(
    r"^localhost(?::[0-9]{1,5})?(?:[/?#].*)?$", re.IGNORECASE
)
_BRACKETED_IPV6_RE = re.compile(
    r"^\[[0-9a-fA-F:.%]+\](?::[0-9]{1,5})?(?:[/?#].*)?$"
)


def looks_like_url(text: str) -> bool:
    """Heuristic: does this omnibox text look like a URL/domain rather than
    a search query?"""
    text = text.strip()
    if not text or " " in text:
        return False
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", text):
        return True
    try:
        ipaddress.ip_address(text)
        return True
    except ValueError:
        pass
    if _LOCALHOST_RE.match(text):
        return True
    if text.lower().startswith("www."):
        return True
    host_part = re.split(r"[/?#]", text, maxsplit=1)[0]
    host_without_port = host_part.rsplit(":", 1)[0] if ":" in host_part else host_part
    try:
        ipaddress.ip_address(host_without_port.strip("[]"))
        return True
    except ValueError:
        pass
    if _BRACKETED_IPV6_RE.match(text):
        return True
    if _HOSTNAME_RE.match(text):
        return True
    return False


def build_navigation_url(text: str, search_engine: str) -> QUrl:
    """Turn omnibox text into a QUrl — either the (upgraded) address itself,
    or a search-engine query URL. SEARCH_ENGINES values are bare URL
    prefixes (no placeholder token) — the query is percent-encoded and
    appended directly, so adding a new engine is just one dict entry."""
    text = text.strip()
    if looks_like_url(text):
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", text):
            host_part = re.split(r"[/?#]", text, maxsplit=1)[0]
            try:
                address = ipaddress.ip_address(host_part)
                if address.version == 6:
                    text = f"[{host_part}]" + text[len(host_part):]
            except ValueError:
                pass
            text = "https://" + text
        return QUrl(text)

    base_url = SEARCH_ENGINES.get(search_engine, SEARCH_ENGINES["Google"])
    return QUrl(base_url + quote_plus(text))


def parse_search_pseudo_url(url: QUrl, search_engine: str) -> QUrl | None:
    """If `url` is the arkbrowse://search?q=... pseudo-URL emitted by the
    New Tab page's search box (see build_start_page_html's <script>), return
    the real navigation target it represents — computed via the exact same
    build_navigation_url() heuristic the omnibox uses. Returns None for any
    other URL, meaning "not ours, let it navigate normally"."""
    if url.scheme() == "arkbrowse" and url.host() == "search":
        query_text = QUrlQuery(url).queryItemValue(
            "q", QUrl.ComponentFormattingOption.FullyDecoded
        )
        return build_navigation_url(query_text, search_engine)
    return None


# ---------------------------------------------------------------------------
# Start-page logo — embedded as base64 in the New Tab page's HTML (the
# toolbar itself intentionally has no logo; see build_start_page_html).
# ---------------------------------------------------------------------------

_LOGO_BASE64_CACHE: str | None = None


def _logo_base64() -> str:
    """Read+encode logo.png once and cache it, for embedding directly in the
    New Tab page's HTML as a data: URI. Embedding avoids any relative-path
    resolution headaches for a page loaded via setHtml() rather than from a
    real file:// or http(s):// URL."""
    global _LOGO_BASE64_CACHE
    if _LOGO_BASE64_CACHE is None:
        logo_path = resource_path("logo.png")
        try:
            with open(logo_path, "rb") as f:
                _LOGO_BASE64_CACHE = base64.b64encode(f.read()).decode("ascii")
        except OSError:
            _LOGO_BASE64_CACHE = ""
    return _LOGO_BASE64_CACHE


def build_start_page_html(palette: dict, search_engine: str, incognito: bool = False) -> str:
    """arkBrowse's own New Tab / home page: logo + centered search bar,
    themed to match the active color theme. Submitting the form navigates
    via the arkbrowse://search pseudo-URL, which ArkWebEnginePage below
    intercepts and turns into a real navigation using the same
    URL-vs-search heuristic as the omnibox (build_navigation_url)."""
    accent = INCOGNITO_ACCENT if incognito else palette["accent"]
    logo_b64 = _logo_base64()
    if logo_b64:
        logo_html = f'<img class="logo" src="data:image/png;base64,{logo_b64}" alt="arkBrowse">'
    else:
        logo_html = '<div class="logo-text">arkBrowse</div>'

    incognito_note = ""
    if incognito:
        incognito_note = (
            '<div class="incognito-note">You\u2019re browsing privately '
            "in an Incognito window \u2014 nothing here is saved.</div>"
        )

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>New Tab</title>
<style>
  * {{ box-sizing: border-box; }}
  html, body {{
    margin: 0; height: 100%; background: {palette['bg']};
    font-family: "Segoe UI", "Inter", "Helvetica Neue", Arial, sans-serif;
  }}
  .wrap {{
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    height: 100%; padding: 24px;
  }}
  img.logo {{
    height: 128px; margin-bottom: 32px; user-select: none; -webkit-user-drag: none;
    filter: brightness(1.5) saturate(1.6);
  }}
  .logo-text {{
    font-size: 34px; font-weight: 700; color: {palette['text']}; margin-bottom: 32px;
  }}
  form {{ width: 560px; max-width: 90vw; }}
  input[type="text"] {{
    width: 100%; padding: 15px 22px; font-size: 16px; border-radius: 26px;
    border: 1px solid {palette['border']}; outline: none;
    background: {palette['elevated']}; color: {palette['text']};
  }}
  input[type="text"]:focus {{ border-color: {accent}; }}
  .tagline {{
    color: {palette['text_dim']}; margin-top: 18px; font-size: 13px; letter-spacing: 0.3px;
  }}
  .incognito-note {{ color: {accent}; margin-top: 10px; font-size: 12.5px; font-weight: 600; }}
</style>
</head>
<body>
  <div class="wrap">
    {logo_html}
    <form id="ark-search-form">
      <input type="text" id="ark-search-input" autofocus
             placeholder="Search {search_engine} or type a web address">
    </form>
    <div class="tagline">A Modern Gateway to a Safer Web</div>
    {incognito_note}
  </div>
  <script>
    document.getElementById('ark-search-form').addEventListener('submit', function (e) {{
      e.preventDefault();
      var q = document.getElementById('ark-search-input').value.trim();
      if (!q) return;
      window.location.href = 'arkbrowse://search?q=' + encodeURIComponent(q);
    }});
  </script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Settings dialog.
# ---------------------------------------------------------------------------

class SettingsDialog(QDialog):
    def __init__(self, settings_manager: SettingsManager, on_apply, parent=None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.on_apply = on_apply

        self.setWindowTitle(f"{APP_NAME} Settings")
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)

        title = QLabel("Appearance")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(10)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(list(THEME_PALETTES.keys()))
        self.theme_combo.setCurrentText(settings_manager.get("theme_name"))
        form.addRow("Color theme:", self.theme_combo)

        layout.addLayout(form)

        browsing_title = QLabel("Browsing")
        browsing_title.setObjectName("SectionTitle")
        layout.addWidget(browsing_title)

        form2 = QFormLayout()
        form2.setSpacing(10)

        self.startpage_check = QCheckBox("Use the arkBrowse start page as my homepage")
        homepage_is_startpage = settings_manager.get("homepage_url") in (NEW_TAB_URL, "arkbrowse:newtab", "")
        self.startpage_check.setChecked(homepage_is_startpage)
        form2.addRow("", self.startpage_check)

        self.homepage_edit = QLineEdit(
            "" if homepage_is_startpage else settings_manager.get("homepage_url")
        )
        self.homepage_edit.setPlaceholderText("https://example.com")
        self.homepage_edit.setEnabled(not homepage_is_startpage)
        self.startpage_check.toggled.connect(lambda checked: self.homepage_edit.setEnabled(not checked))
        form2.addRow("Custom homepage:", self.homepage_edit)

        self.search_combo = QComboBox()
        self.search_combo.addItems(list(SEARCH_ENGINES.keys()))
        self.search_combo.setCurrentText(settings_manager.get("default_search_engine"))
        form2.addRow("Default search engine:", self.search_combo)

        layout.addLayout(form2)

        security_title = QLabel("Security & Privacy")
        security_title.setObjectName("SectionTitle")
        layout.addWidget(security_title)

        self.adblock_check = QCheckBox("Block ads & known trackers")
        self.adblock_check.setChecked(bool(settings_manager.get("adblock_enabled")))
        layout.addWidget(self.adblock_check)

        self.https_check = QCheckBox("Force-upgrade http:// links to https://")
        self.https_check.setChecked(bool(settings_manager.get("force_https_enabled")))
        layout.addWidget(self.https_check)

        privacy_title = QLabel("Privacy & compatibility")
        privacy_title.setObjectName("SectionTitle")
        layout.addWidget(privacy_title)

        self.javascript_check = QCheckBox("Allow JavaScript (required by most modern sites)")
        self.javascript_check.setChecked(bool(settings_manager.get("javascript_enabled")))
        layout.addWidget(self.javascript_check)

        self.autoplay_check = QCheckBox("Require a click before media can autoplay")
        self.autoplay_check.setChecked(
            bool(settings_manager.get("autoplay_requires_user_gesture"))
        )
        layout.addWidget(self.autoplay_check)

        privacy_note = QLabel(
            "Browsing history, cookies, cache, downloads, and form data are "
            "kept in memory only and are discarded when arkBrowse closes."
        )
        privacy_note.setWordWrap(True)
        privacy_note.setObjectName("HintLabel")
        layout.addWidget(privacy_note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        save_btn = buttons.button(QDialogButtonBox.StandardButton.Save)
        save_btn.setObjectName("PrimaryButton")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self) -> None:
        if self.startpage_check.isChecked():
            homepage = NEW_TAB_URL
        else:
            homepage = self.homepage_edit.text().strip()
            if not homepage:
                homepage = NEW_TAB_URL
            elif not homepage.startswith(("http://", "https://")):
                homepage = "https://" + homepage

        self.settings_manager.set("theme_name", self.theme_combo.currentText())
        self.settings_manager.set("homepage_url", homepage)
        self.settings_manager.set("default_search_engine", self.search_combo.currentText())
        self.settings_manager.set("adblock_enabled", self.adblock_check.isChecked())
        self.settings_manager.set("force_https_enabled", self.https_check.isChecked())
        self.settings_manager.set("javascript_enabled", self.javascript_check.isChecked())
        self.settings_manager.set(
            "autoplay_requires_user_gesture", self.autoplay_check.isChecked()
        )
        self.settings_manager.save()

        self.on_apply()
        self.accept()


# ---------------------------------------------------------------------------
# A single browser tab.
# ---------------------------------------------------------------------------

def apply_profile_settings(profile: QWebEngineProfile, settings_manager: SettingsManager) -> None:
    """Apply fast, privacy-first WebEngine defaults to a profile.

    Normal and incognito windows both use memory-only profiles.  The normal
    windows share one profile so multiple windows can coexist safely without
    creating duplicate profiles with the same storage name.
    """
    try:
        profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies
        )
        profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
    except AttributeError:
        # Off-the-record profiles already provide these guarantees on older
        # Qt builds; leave the defaults alone if an enum was renamed.
        pass

    web_settings = profile.settings()
    web_settings.setAttribute(
        QWebEngineSettings.WebAttribute.JavascriptEnabled,
        bool(settings_manager.get("javascript_enabled")),
    )
    web_settings.setAttribute(
        QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture,
        bool(settings_manager.get("autoplay_requires_user_gesture")),
    )
    web_settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, False)


def shared_browser_session(settings_manager: SettingsManager):
    """Return the one ephemeral profile/policy shared by normal windows."""
    app = QApplication.instance()
    if app is None:
        raise RuntimeError("QApplication must exist before creating a browser window")

    policy = getattr(app, "arkbrowse_session_policy", None)
    if policy is None:
        policy = BrowserSessionPolicy()
        app.arkbrowse_session_policy = policy

    profile = getattr(app, "arkbrowse_profile", None)
    if profile is None:
        # Unnamed QWebEngineProfile is off-the-record.  Parent it to the
        # application, never to one window, so closing one window cannot
        # destroy the profile used by the others.
        profile = QWebEngineProfile(app)
        interceptor = AdBlockInterceptor(settings_manager, policy, profile)
        profile.setUrlRequestInterceptor(interceptor)
        app.arkbrowse_profile = profile
        app.arkbrowse_interceptor = interceptor
    apply_profile_settings(profile, settings_manager)
    return profile, policy


class ArkWebEnginePage(QWebEnginePage):
    """Custom page that recognizes the arkbrowse://search pseudo-URL used by
    the New Tab page's own search box (see build_start_page_html) and turns
    it into a real navigation using the exact same URL-vs-search heuristic
    as the omnibox (build_navigation_url) — so searching from the New Tab
    page and searching from the address bar always behave identically."""

    def __init__(self, window: "BrowserWindow", profile: QWebEngineProfile, parent=None):
        super().__init__(profile, parent)
        self._window = window

    def acceptNavigationRequest(self, url: QUrl, _nav_type, is_main_frame: bool) -> bool:  # noqa: N802
        engine = self._window.settings_manager.get("default_search_engine")
        target = parse_search_pseudo_url(url, engine)
        if is_main_frame and target is not None:
            # Defer: we're still inside Qt's navigation callback here, and
            # calling setUrl() synchronously from within it can re-enter the
            # navigation machinery. Posting it to the next event-loop tick
            # avoids that entirely.
            QTimer.singleShot(0, lambda p=self, t=target: p.setUrl(t))
            return False
        if is_main_frame and url.scheme().lower() == "http":
            target = self._window.prepare_http_navigation(url)
            if target is None:
                return False
            if target.toString() != url.toString():
                QTimer.singleShot(0, lambda p=self, t=target: p.setUrl(t))
                return False
        return True

    def certificateError(self, error) -> bool:  # noqa: N802
        """Give certificate failures a clear decision instead of a blank page."""
        if not error.isOverridable():
            return False
        description = error.description() or "The site's certificate is invalid."
        box = QMessageBox(self._window)
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle("Certificate warning")
        box.setText("arkBrowse could not verify this website's certificate.")
        box.setInformativeText(
            f"{description}\n\nOnly continue if you trust this site."
        )
        proceed = box.addButton("Proceed anyway", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Go back", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(box.buttons()[-1])
        box.exec()
        if box.clickedButton() is proceed:
            error.acceptCertificate()
            return True
        error.rejectCertificate()
        return False


class BrowserView(QWebEngineView):
    """Thin QWebEngineView subclass so target="_blank" / window.open() links
    open a new tab in the same window instead of vanishing silently."""

    def __init__(self, window: "BrowserWindow", profile: QWebEngineProfile, parent=None):
        super().__init__(parent)
        self._window = window
        self.setPage(ArkWebEnginePage(window, profile, self))

    def createWindow(self, _type):  # noqa: N802 (Qt override name)
        return self._window.add_tab(focus=True)


# ---------------------------------------------------------------------------
# Main browser window (also used, with incognito=True, for private windows).
# ---------------------------------------------------------------------------

class BrowserWindow(QMainWindow):
    def __init__(
        self,
        settings_manager: SettingsManager,
        incognito: bool = False,
        profile: QWebEngineProfile | None = None,
        session_policy: BrowserSessionPolicy | None = None,
    ):
        super().__init__()
        self.settings_manager = settings_manager
        self.incognito = incognito
        if session_policy is None:
            if incognito:
                session_policy = BrowserSessionPolicy()
            else:
                _, session_policy = shared_browser_session(settings_manager)
        self.session_policy = session_policy

        title = f"{APP_NAME}" + (" (Incognito)" if incognito else "")
        self.setWindowTitle(title)
        self.resize(1280, 820)
        # Ensures the window and its pages are actually destroyed when closed.
        # A normal window does not own the shared profile; the application does.
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        icon_path = resource_path("logo.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        if incognito:
            self.profile = profile or QWebEngineProfile(self)
            self.interceptor = AdBlockInterceptor(
                self.settings_manager, self.session_policy, self.profile
            )
            self.profile.setUrlRequestInterceptor(self.interceptor)
        else:
            if profile is None:
                self.profile, self.session_policy = shared_browser_session(
                    settings_manager
                )
            else:
                self.profile = profile
            self.interceptor = getattr(
                QApplication.instance(), "arkbrowse_interceptor", None
            )
            if self.interceptor is None:
                self.interceptor = AdBlockInterceptor(
                    self.settings_manager, self.session_policy, self.profile
                )
                self.profile.setUrlRequestInterceptor(self.interceptor)
        apply_profile_settings(self.profile, self.settings_manager)

        # --- Central tab widget ---
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._on_current_tab_changed)
        self.setCentralWidget(self.tabs)

        new_tab_btn = QPushButton("+")
        new_tab_btn.setFixedSize(28, 28)
        new_tab_btn.setToolTip("New tab (Ctrl+T)")
        new_tab_btn.clicked.connect(lambda: self.add_tab(focus=True))
        self.tabs.setCornerWidget(new_tab_btn, Qt.Corner.TopRightCorner)

        self._build_toolbar()
        self._build_shortcuts()
        self.apply_theme()

        start_url = self.settings_manager.get("homepage_url")
        if start_url in (NEW_TAB_URL, "arkbrowse:newtab", "", None):
            self.add_tab(focus=True)  # url=None => internal start page
        else:
            self.add_tab(url=QUrl(start_url), focus=True)

    # -- UI construction -----------------------------------------------

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Navigation")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(toolbar)

        if self.incognito:
            badge = QLabel("Incognito")
            badge.setObjectName("IncognitoBadge")
            toolbar.addWidget(badge)

        # Icons are colored per-theme and (re)built by _refresh_toolbar_icons(),
        # called once here and again on every apply_theme(). Actions are
        # created icon-only (empty text) — tooltips carry the labels.
        self.back_action = QAction(self)
        self.back_action.setToolTip("Back (Alt+Left)")
        self.back_action.triggered.connect(lambda: self.current_view() and self.current_view().back())
        toolbar.addAction(self.back_action)

        self.forward_action = QAction(self)
        self.forward_action.setToolTip("Forward (Alt+Right)")
        self.forward_action.triggered.connect(lambda: self.current_view() and self.current_view().forward())
        toolbar.addAction(self.forward_action)

        self.reload_action = QAction(self)
        self.reload_action.setToolTip("Reload (Ctrl+R)")
        self.reload_action.triggered.connect(self._reload_current)
        toolbar.addAction(self.reload_action)

        self.home_action = QAction(self)
        self.home_action.setToolTip("Home")
        self.home_action.triggered.connect(self._go_home)
        toolbar.addAction(self.home_action)

        self.new_window_action = QAction(self)
        self.new_window_action.setToolTip("New Window (Ctrl+N)")
        self.new_window_action.triggered.connect(self._open_new_window)
        toolbar.addAction(self.new_window_action)

        self.security_icon = QLabel()
        self.security_icon.setObjectName("SecurityIcon")
        toolbar.addWidget(self.security_icon)

        self.omnibox = QLineEdit()
        self.omnibox.setObjectName("Omnibox")
        self.omnibox.setPlaceholderText("Search or enter a website address")
        self.omnibox.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.omnibox.returnPressed.connect(self._navigate_from_omnibox)
        toolbar.addWidget(self.omnibox)

        go_action = QAction("Go", self)
        go_action.triggered.connect(self._navigate_from_omnibox)
        toolbar.addAction(go_action)

        self.incognito_action = QAction(self)
        self.incognito_action.setToolTip("New Incognito Window (Ctrl+Shift+N)")
        self.incognito_action.triggered.connect(self._open_incognito_window)
        toolbar.addAction(self.incognito_action)

        self.settings_action = QAction(self)
        self.settings_action.setToolTip("Settings")
        self.settings_action.triggered.connect(self._open_settings)
        toolbar.addAction(self.settings_action)

        self._refresh_toolbar_icons()

    def _build_shortcuts(self) -> None:
        shortcuts = [
            (QKeySequence("Ctrl+T"), lambda: self.add_tab(focus=True)),
            (QKeySequence("Ctrl+N"), self._open_new_window),
            (QKeySequence("Ctrl+W"), lambda: self.close_tab(self.tabs.currentIndex())),
            (QKeySequence("Ctrl+L"), self._focus_omnibox),
            (QKeySequence("Ctrl+R"), self._reload_current),
            (QKeySequence("F5"), self._reload_current),
            (QKeySequence("Ctrl+Shift+N"), self._open_incognito_window),
            (QKeySequence("Alt+Left"), lambda: self.current_view() and self.current_view().back()),
            (QKeySequence("Alt+Right"), lambda: self.current_view() and self.current_view().forward()),
        ]
        for keyseq, handler in shortcuts:
            action = QAction(self)
            action.setShortcut(keyseq)
            action.triggered.connect(handler)
            self.addAction(action)

    # -- Tab management ---------------------------------------------------

    def current_view(self) -> BrowserView | None:
        return self.tabs.currentWidget()

    def add_tab(self, url: QUrl | None = None, focus: bool = False) -> BrowserView:
        view = BrowserView(self, self.profile)
        index = self.tabs.addTab(view, "New Tab")

        view.titleChanged.connect(lambda title, v=view: self._on_title_changed(v, title))
        view.iconChanged.connect(lambda icon, v=view: self._on_icon_changed(v, icon))
        view.urlChanged.connect(lambda qurl, v=view: self._on_url_changed(v, qurl))
        view.loadStarted.connect(lambda v=view: self._on_load_started(v))
        view.loadFinished.connect(lambda ok, v=view: self._on_load_finished(v, ok))

        if url is None or not url.toString():
            # A blank new tab (Ctrl+T, "+" button, or the window's very
            # first tab) always opens arkBrowse's own start page — never a
            # real website — matching how Chrome/Edge's New Tab page works.
            self._show_start_page(view)
        else:
            view.setUrl(url)

        if focus:
            self.tabs.setCurrentIndex(index)
            self.omnibox.setFocus()
        return view

    def _show_start_page(self, view: BrowserView) -> None:
        """Render arkBrowse's own logo+search-bar start page into `view`,
        entirely locally via setHtml() — no network request is made."""
        theme_name = self.settings_manager.get("theme_name")
        palette = THEME_PALETTES.get(theme_name, THEME_PALETTES["Obsidian Dark"])
        engine = self.settings_manager.get("default_search_engine")
        html = build_start_page_html(palette, engine, incognito=self.incognito)
        view.setHtml(html, QUrl(NEW_TAB_URL))

    def close_tab(self, index: int) -> None:
        if index < 0:
            return
        widget = self.tabs.widget(index)
        self.tabs.removeTab(index)
        if widget is not None:
            widget.deleteLater()
        if self.tabs.count() == 0:
            self.add_tab(focus=True)

    def _on_current_tab_changed(self, _index: int) -> None:
        view = self.current_view()
        if view is not None:
            self._sync_omnibox_and_security(view.url())
            self._update_reload_action(view)

    # -- Per-tab signal handlers ------------------------------------------

    def _on_title_changed(self, view: BrowserView, title: str) -> None:
        index = self.tabs.indexOf(view)
        if index != -1:
            display = title if title else "New Tab"
            self.tabs.setTabText(index, display[:24] + ("…" if len(display) > 24 else ""))
            self.tabs.setTabToolTip(index, title)

    def _on_icon_changed(self, view: BrowserView, icon) -> None:
        index = self.tabs.indexOf(view)
        if index != -1 and not icon.isNull():
            self.tabs.setTabIcon(index, icon)

    def _on_url_changed(self, view: BrowserView, qurl: QUrl) -> None:
        if view is self.current_view():
            self._sync_omnibox_and_security(qurl)

    def _on_load_started(self, view: BrowserView) -> None:
        view.setProperty("ark_loading", True)
        if view is self.current_view():
            self.reload_action.setIcon(self._icon_stop)
            self.reload_action.setToolTip("Stop")

    def _on_load_finished(self, view: BrowserView, _ok: bool) -> None:
        view.setProperty("ark_loading", False)
        if view is self.current_view():
            self.reload_action.setIcon(self._icon_reload)
            self.reload_action.setToolTip("Reload (Ctrl+R)")

    def _sync_omnibox_and_security(self, qurl: QUrl) -> None:
        """Keep the omnibox text and the padlock icon consistent with the
        currently-shown page. The internal start page shows a blank
        omnibox (like Chrome's New Tab page) rather than the literal
        'arkbrowse://newtab' sentinel."""
        if qurl.scheme() == "arkbrowse":
            self.omnibox.setText("")
        else:
            self.omnibox.setText(qurl.toString())
        self._update_security_icon(qurl)

    def _update_security_icon(self, qurl: QUrl) -> None:
        if qurl.scheme() == "arkbrowse":
            # No security indicator needed for arkBrowse's own local page —
            # showing a house icon here would just duplicate the adjacent
            # Home button. Real browsers do the same: Chrome shows nothing
            # in the address-bar icon slot on its New Tab page either.
            self.security_icon.clear()
            self.security_icon.setToolTip("")
        elif qurl.scheme() == "https":
            self.security_icon.setPixmap(self._icon_lock_closed.pixmap(18, 18))
            self.security_icon.setToolTip("Secure connection (HTTPS)")
        else:
            self.security_icon.setPixmap(self._icon_lock_open.pixmap(18, 18))
            self.security_icon.setToolTip("Not secure")

    # -- Navigation actions -------------------------------------------------

    def _navigate_from_omnibox(self) -> None:
        text = self.omnibox.text().strip()
        if not text:
            return
        view = self.current_view() or self.add_tab(focus=True)
        if text in (NEW_TAB_URL, "arkbrowse:newtab"):
            self._show_start_page(view)
            return
        url = build_navigation_url(text, self.settings_manager.get("default_search_engine"))
        target = self.prepare_http_navigation(url)
        if target is not None:
            view.setUrl(target)

    def _reload_current(self) -> None:
        view = self.current_view()
        if view is None:
            return
        if bool(view.property("ark_loading")):
            view.stop()
        else:
            view.reload()

    def _go_home(self) -> None:
        view = self.current_view() or self.add_tab(focus=True)
        homepage = self.settings_manager.get("homepage_url")
        if homepage in (NEW_TAB_URL, "arkbrowse:newtab", "", None):
            self._show_start_page(view)
        else:
            view.setUrl(QUrl(homepage))

    def _focus_omnibox(self) -> None:
        self.omnibox.setFocus()
        self.omnibox.selectAll()

    # -- Settings / theming ------------------------------------------------

    def apply_theme(self) -> None:
        theme_name = self.settings_manager.get("theme_name")
        palette = THEME_PALETTES.get(theme_name, THEME_PALETTES["Obsidian Dark"])
        self.setStyleSheet(build_stylesheet(palette, incognito=self.incognito))
        self._refresh_toolbar_icons()
        apply_windows_titlebar_theme(self, dark=(theme_name != "Classic Light"))

        # Any tab currently showing the internal start page is re-rendered
        # immediately so it picks up the new theme colors too — otherwise
        # it would keep showing whatever palette was active when it loaded.
        for i in range(self.tabs.count()):
            view = self.tabs.widget(i)
            if view is not None and view.url().scheme() == "arkbrowse":
                self._show_start_page(view)

    def _refresh_toolbar_icons(self) -> None:
        """(Re)build every toolbar icon in the current theme's text color,
        so icons always match the theme instead of staying whatever color
        they were generated in originally. Called once during toolbar
        construction and again on every theme switch."""
        theme_name = self.settings_manager.get("theme_name")
        palette = THEME_PALETTES.get(theme_name, THEME_PALETTES["Obsidian Dark"])
        color = palette["text"]

        self._icon_reload = make_svg_icon("reload", color)
        self._icon_stop = make_svg_icon("stop", color)
        self._icon_home = make_svg_icon("home", color)
        self._icon_lock_closed = make_svg_icon("lock_closed", color)
        self._icon_lock_open = make_svg_icon("lock_open", color)
        self._icon_window = make_svg_icon("window", color)

        self.back_action.setIcon(make_svg_icon("back", color))
        self.forward_action.setIcon(make_svg_icon("forward", color))
        self.reload_action.setIcon(self._icon_reload)
        self.home_action.setIcon(self._icon_home)
        self.new_window_action.setIcon(self._icon_window)
        self.incognito_action.setIcon(make_svg_icon("incognito", color))
        self.settings_action.setIcon(make_svg_icon("settings", color))

        # Refresh the padlock/start-page indicator too, using whatever the
        # current tab's URL actually is (not just a static icon).
        view = self.current_view()
        if view is not None:
            self._update_security_icon(view.url())
            self._update_reload_action(view)

    def _update_reload_action(self, view: BrowserView | None = None) -> None:
        view = view or self.current_view()
        if view is not None and bool(view.property("ark_loading")):
            self.reload_action.setIcon(self._icon_stop)
            self.reload_action.setToolTip("Stop")
        else:
            self.reload_action.setIcon(self._icon_reload)
            self.reload_action.setToolTip("Reload (Ctrl+R)")

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.settings_manager, on_apply=self._on_settings_applied, parent=self)
        dialog.exec()

    def _on_settings_applied(self) -> None:
        # Theme applies instantly to every open window, not just this one.
        app = QApplication.instance()
        for widget in app.topLevelWidgets():
            if isinstance(widget, BrowserWindow):
                apply_profile_settings(widget.profile, widget.settings_manager)
                widget.apply_theme()

    def _open_incognito_window(self) -> None:
        window = BrowserWindow(self.settings_manager, incognito=True)
        app = QApplication.instance()
        app.arkbrowse_windows.append(window)
        window.show()

    def _open_new_window(self) -> None:
        """Open a normal window on the already-created ephemeral profile."""
        window = BrowserWindow(
            self.settings_manager,
            incognito=False,
            profile=self.profile,
            session_policy=self.session_policy,
        )
        app = QApplication.instance()
        app.arkbrowse_windows.append(window)
        window.show()

    def prepare_http_navigation(self, url: QUrl) -> QUrl | None:
        """Ask before remote HTTP and keep any exception in memory only."""
        if (
            url.scheme().lower() != "http"
            or not url.host()
            or self.interceptor._is_local_host(url.host())
            or self.session_policy.allows_http(url)
        ):
            return url

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Insecure HTTP connection")
        box.setText("This website is using an unencrypted HTTP connection.")

        if self.settings_manager.get("force_https_enabled"):
            box.setInformativeText(
                "HTTPS is safer. Use HTTPS if the site supports it, or continue "
                "over HTTP only if you trust this site."
            )
            use_https = box.addButton(
                "Use HTTPS", QMessageBox.ButtonRole.AcceptRole
            )
            continue_http = box.addButton(
                "Continue over HTTP", QMessageBox.ButtonRole.DestructiveRole
            )
            box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
            box.setDefaultButton(use_https)
            box.exec()
            if box.clickedButton() is use_https:
                upgraded = QUrl(url)
                upgraded.setScheme("https")
                return upgraded
            if box.clickedButton() is continue_http:
                self.session_policy.allow_http(url)
                return url
            return None

        box.setInformativeText(
            "This connection is not secure. Continue only if you understand "
            "that traffic can be intercepted."
        )
        continue_http = box.addButton(
            "Continue over HTTP", QMessageBox.ButtonRole.DestructiveRole
        )
        box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(box.buttons()[-1])
        box.exec()
        if box.clickedButton() is continue_http:
            self.session_policy.allow_http(url)
            return url
        return None

    # -- Shutdown / teardown ------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override name)
        # Tear down every page explicitly before the window disappears. This
        # is important for incognito profiles owned by this window and also
        # prevents a normal window from leaving live pages attached to the
        # application-owned shared profile.
        while self.tabs.count():
            view = self.tabs.widget(0)
            self.tabs.removeTab(0)
            if view is not None:
                page = view.page()
                if page is not None:
                    page.deleteLater()
                view.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

        app = QApplication.instance()
        if app is not None and hasattr(app, "arkbrowse_windows") and self in app.arkbrowse_windows:
            app.arkbrowse_windows.remove(self)

        super().closeEvent(event)


# ---------------------------------------------------------------------------
# Entry point.
# ---------------------------------------------------------------------------

def main() -> int:
    QApplication.setApplicationName(APP_NAME)
    QApplication.setOrganizationName(ORG_NAME)
    QApplication.setApplicationVersion(APP_VERSION)

    app = QApplication(sys.argv)
    app.arkbrowse_windows = []  # keep strong references so windows aren't GC'd
    app.arkbrowse_session_policy = BrowserSessionPolicy()
    app.arkbrowse_profile = None
    app.arkbrowse_interceptor = None

    def _shutdown_cleanup() -> None:
        # Safety net: make sure every window's closeEvent (which tears
        # down its tabs/pages before its profile) has actually run before
        # the application object itself goes away, no matter which code
        # path triggered the quit.
        for win in list(app.arkbrowse_windows):
            win.close()
        # closeEvent queues page/view destruction. Flush that queue before
        # QApplication destroys its application-owned shared profile.
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    app.aboutToQuit.connect(_shutdown_cleanup)

    settings_manager = SettingsManager()

    window = BrowserWindow(settings_manager, incognito=False)
    app.arkbrowse_windows.append(window)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

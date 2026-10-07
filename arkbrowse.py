#!/usr/bin/env python3
"""
arkBrowse — Fast, Secure, Obsidian-Dark Web Browsing.

A modern, security-focused desktop web browser built with PyQt6 and
QtWebEngine (Chromium).
"""

from __future__ import annotations

import sys
from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtWidgets import QApplication

# Re-export all symbols so that tests, shortcuts, and any external scripts
# have 100% full backwards compatibility with the original module structure.
from core.config import (
    APP_NAME,
    APP_VERSION,
    DEFAULT_SETTINGS,
    INCOGNITO_ACCENT,
    NEW_TAB_URL,
    ORG_NAME,
    SEARCH_ENGINES,
    SETTINGS_VERSION,
    THEME_PALETTES,
    resource_path,
    settings_file_path,
)
from core.dialogs import SettingsDialog
from core.network import (
    FALLBACK_BLOCKED_DOMAINS,
    AdBlockInterceptor,
    BrowserSessionPolicy,
    load_blocked_domains,
    parse_filter_list,
)
from core.settings import SettingsManager
from core.startpage import (
    _logo_base64,
    build_navigation_url,
    build_start_page_html,
    looks_like_url,
    parse_search_pseudo_url,
)
from core.styles import (
    apply_windows_titlebar_theme,
    build_stylesheet,
    make_svg_icon,
)
from core.views import (
    ArkWebEnginePage,
    BrowserView,
    apply_profile_settings,
    shared_browser_session,
)
from core.window import BrowserWindow


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
        for win in list(app.arkbrowse_windows):
            win.close()
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

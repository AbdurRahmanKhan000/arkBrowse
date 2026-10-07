"""Configuration constants and path resolution for arkBrowse."""

from __future__ import annotations

import os
import sys

APP_NAME = "arkBrowse"
APP_VERSION = "1.1.0"
ORG_NAME = "arkBrowse"
SETTINGS_VERSION = 2

NEW_TAB_URL = "arkbrowse://newtab"

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

INCOGNITO_ACCENT = "#7C3AED"


def resource_path(relative_path: str) -> str:
    """Resolve a bundled resource whether running from source or PyInstaller bundle."""
    base_path = getattr(sys, "_MEIPASS", os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    # Check directly beside script first
    direct = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")), relative_path)
    if os.path.exists(direct):
        return direct
    return os.path.join(base_path, relative_path)


def settings_file_path() -> str:
    """Return a per-user preferences path."""
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

"""Settings management for arkBrowse."""

from __future__ import annotations

import json
import os
import tempfile

from .config import (
    DEFAULT_SETTINGS,
    SETTINGS_VERSION,
    SEARCH_ENGINES,
    THEME_PALETTES,
    settings_file_path,
)


class SettingsManager:
    """Loads/saves a flat dict of user preferences to settings.json."""

    def __init__(self, path: str | None = None):
        self._explicit_path = path is not None
        self.path = path or settings_file_path()
        self.data: dict = dict(DEFAULT_SETTINGS)
        self.load()

    def load(self) -> None:
        source_path = self.path
        if not os.path.exists(source_path) and not self._explicit_path:
            legacy_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "settings.json"
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

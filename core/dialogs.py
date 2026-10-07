"""Dialog windows for arkBrowse."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from .config import (
    APP_NAME,
    NEW_TAB_URL,
    SEARCH_ENGINES,
    THEME_PALETTES,
)
from .settings import SettingsManager


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

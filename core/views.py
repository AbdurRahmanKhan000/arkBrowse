"""Web engine page and view components, including custom context menu."""

from __future__ import annotations

import os
from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtGui import QAction, QContextMenuEvent, QKeySequence
from PyQt6.QtPrintSupport import QPrintDialog, QPrinter
from PyQt6.QtWebEngineCore import (
    QWebEngineContextMenuRequest,
    QWebEngineDownloadRequest,
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineSettings,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMenu,
    QMessageBox,
)

from .network import (
    AdBlockInterceptor,
    BrowserSessionPolicy,
)
from .settings import SettingsManager
from .startpage import parse_search_pseudo_url
from .styles import make_svg_icon


def handle_download_requested(download: QWebEngineDownloadRequest) -> None:
    """Prompt the user with a standard 'Save As' dialog for file, image, or page downloads."""
    suggested = download.downloadFileName() or "download"
    default_dir = os.path.expanduser("~/Downloads")
    default_path = os.path.join(default_dir, suggested)

    if download.isSavePageDownload():
        filter_str = (
            "Webpage, Complete (*.html *.htm);;"
            "Webpage, Single File (*.mhtml);;"
            "Webpage, HTML Only (*.html *.htm);;"
            "All Files (*.*)"
        )
    else:
        ext = os.path.splitext(suggested)[1].lower()
        if ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"):
            filter_str = f"Image Files (*{ext});;All Files (*.*)"
        else:
            filter_str = "All Files (*.*)"

    active_win = QApplication.activeWindow()
    file_path, selected_filter = QFileDialog.getSaveFileName(
        active_win,
        "Save File" if not download.isSavePageDownload() else "Save Page As",
        default_path,
        filter_str,
    )

    if not file_path:
        download.cancel()
        return

    folder, filename = os.path.split(file_path)
    download.setDownloadDirectory(folder)
    download.setDownloadFileName(filename)

    if download.isSavePageDownload():
        if "Single File" in selected_filter:
            download.setSavePageFormat(QWebEngineDownloadRequest.SavePageFormat.MimeHtmlSaveFormat)
        elif "HTML Only" in selected_filter:
            download.setSavePageFormat(QWebEngineDownloadRequest.SavePageFormat.SingleHtmlSaveFormat)
        else:
            download.setSavePageFormat(QWebEngineDownloadRequest.SavePageFormat.CompleteHtmlSaveFormat)

    download.accept()


def apply_profile_settings(profile: QWebEngineProfile, settings_manager: SettingsManager) -> None:
    """Apply fast, privacy-first WebEngine defaults to a profile."""
    try:
        profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies
        )
        profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
    except AttributeError:
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

    # Wire download requested handler once per profile
    if not getattr(profile, "_download_connected", False):
        profile.downloadRequested.connect(handle_download_requested)
        profile._download_connected = True


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
        profile = QWebEngineProfile(app)
        interceptor = AdBlockInterceptor(settings_manager, policy, profile)
        profile.setUrlRequestInterceptor(interceptor)
        app.arkbrowse_profile = profile
        app.arkbrowse_interceptor = interceptor
    apply_profile_settings(profile, settings_manager)
    return profile, policy


class ArkWebEnginePage(QWebEnginePage):
    """Custom page for navigation interception, certificate errors, and search handling."""

    def __init__(self, window, profile: QWebEngineProfile, parent=None):
        super().__init__(profile, parent)
        self._window = window

    def acceptNavigationRequest(self, url: QUrl, _nav_type, is_main_frame: bool) -> bool:  # noqa: N802
        engine = self._window.settings_manager.get("default_search_engine")
        target = parse_search_pseudo_url(url, engine)
        if is_main_frame and target is not None:
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
    """QWebEngineView with custom single-tab window handling and strictly controlled context menu."""

    def __init__(self, window, profile: QWebEngineProfile, parent=None):
        super().__init__(parent)
        self._window = window
        self.setPage(ArkWebEnginePage(window, profile, self))

    def createWindow(self, _type):  # noqa: N802
        return self._window.add_tab(focus=True)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # noqa: N802
        """Display a clean, interactive context menu.
        Shows Back, Forward, Reload, Save as..., Print..., plus context-sensitive
        image and link options (Save image as..., Copy image, Copy link address)
        when right-clicking media or hyperlinks.
        """
        menu = QMenu(self)

        # Get color for icons
        theme_name = self._window.settings_manager.get("theme_name")
        from .config import THEME_PALETTES
        palette = THEME_PALETTES.get(theme_name, THEME_PALETTES["Obsidian Dark"])
        color = palette["text"]

        req = self.lastContextMenuRequest() if hasattr(self, "lastContextMenuRequest") else None
        is_image = False
        is_link = False

        if req is not None:
            try:
                is_image = req.mediaType() == QWebEngineContextMenuRequest.MediaType.MediaTypeImage
            except Exception:
                is_image = False
            try:
                is_link = bool(req.linkUrl() and req.linkUrl().isValid() and req.linkUrl().toString())
            except Exception:
                is_link = False

        # --- Context-specific actions: Image ---
        if is_image:
            save_img_action = QAction(make_svg_icon("image", color), "Save image as...", menu)
            save_img_action.triggered.connect(
                lambda: self.page().triggerAction(QWebEnginePage.WebAction.DownloadImageToDisk)
            )
            menu.addAction(save_img_action)

            copy_img_action = QAction(make_svg_icon("copy", color), "Copy image", menu)
            copy_img_action.triggered.connect(
                lambda: self.page().triggerAction(QWebEnginePage.WebAction.CopyImageToClipboard)
            )
            menu.addAction(copy_img_action)

            copy_img_url_action = QAction(make_svg_icon("link", color), "Copy image address", menu)
            copy_img_url_action.triggered.connect(
                lambda: self.page().triggerAction(QWebEnginePage.WebAction.CopyImageUrlToClipboard)
            )
            menu.addAction(copy_img_url_action)

            menu.addSeparator()

        # --- Context-specific actions: Link ---
        if is_link:
            open_link_tab_action = QAction(make_svg_icon("window", color), "Open link in new tab", menu)
            open_link_tab_action.triggered.connect(
                lambda: self.page().triggerAction(QWebEnginePage.WebAction.OpenLinkInNewTab)
            )
            menu.addAction(open_link_tab_action)

            copy_link_action = QAction(make_svg_icon("link", color), "Copy link address", menu)
            copy_link_action.triggered.connect(
                lambda: self.page().triggerAction(QWebEnginePage.WebAction.CopyLinkToClipboard)
            )
            menu.addAction(copy_link_action)

            menu.addSeparator()

        # --- Standard Navigation Actions ---
        back_action = QAction(make_svg_icon("back", color), "Back", menu)
        back_action.setShortcut(QKeySequence("Alt+Left"))
        back_action.setEnabled(self.history().canGoBack())
        back_action.triggered.connect(self.back)
        menu.addAction(back_action)

        forward_action = QAction(make_svg_icon("forward", color), "Forward", menu)
        forward_action.setShortcut(QKeySequence("Alt+Right"))
        forward_action.setEnabled(self.history().canGoForward())
        forward_action.triggered.connect(self.forward)
        menu.addAction(forward_action)

        reload_action = QAction(make_svg_icon("reload", color), "Reload", menu)
        reload_action.setShortcut(QKeySequence("Ctrl+R"))
        reload_action.triggered.connect(self.reload)
        menu.addAction(reload_action)

        menu.addSeparator()

        save_action = QAction(make_svg_icon("save", color), "Save as...", menu)
        save_action.setShortcut(QKeySequence("Ctrl+S"))
        save_action.triggered.connect(
            lambda: self.page().triggerAction(QWebEnginePage.WebAction.SavePage)
        )
        menu.addAction(save_action)

        print_action = QAction(make_svg_icon("print", color), "Print...", menu)
        print_action.setShortcut(QKeySequence("Ctrl+P"))
        print_action.triggered.connect(self._print_page)
        menu.addAction(print_action)

        menu.exec(event.globalPos())

    def _print_page(self) -> None:
        """Trigger native print dialog and print the current webpage."""
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() == QPrintDialog.DialogCode.Accepted:
            self.page().print(printer, lambda success: None)

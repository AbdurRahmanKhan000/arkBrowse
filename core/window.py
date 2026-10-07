"""BrowserWindow implementation."""

from __future__ import annotations

import os
from PyQt6.QtCore import (
    QCoreApplication,
    QEvent,
    QSize,
    Qt,
    QUrl,
)
from PyQt6.QtGui import QAction, QIcon, QKeySequence
from PyQt6.QtWebEngineCore import QWebEngineProfile
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QToolBar,
)

from .config import (
    APP_NAME,
    NEW_TAB_URL,
    THEME_PALETTES,
    resource_path,
)
from .dialogs import SettingsDialog
from .network import (
    AdBlockInterceptor,
    BrowserSessionPolicy,
)
from .settings import SettingsManager
from .startpage import (
    build_navigation_url,
    build_start_page_html,
)
from .styles import (
    apply_windows_titlebar_theme,
    build_stylesheet,
    make_svg_icon,
)
from .views import (
    BrowserView,
    apply_profile_settings,
    shared_browser_session,
)


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

        # Tabs
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
            self.add_tab(focus=True)
        else:
            self.add_tab(url=QUrl(start_url), focus=True)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Navigation")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(toolbar)

        if self.incognito:
            badge = QLabel("Incognito")
            badge.setObjectName("IncognitoBadge")
            toolbar.addWidget(badge)

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
            (QKeySequence("Ctrl+S"), lambda: self.current_view() and self.current_view().page().triggerAction(self.current_view().page().WebAction.SavePage)),
            (QKeySequence("Ctrl+P"), lambda: self.current_view() and self.current_view()._print_page()),
        ]
        for keyseq, handler in shortcuts:
            action = QAction(self)
            action.setShortcut(keyseq)
            action.triggered.connect(handler)
            self.addAction(action)

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
            self._show_start_page(view)
        else:
            view.setUrl(url)

        if focus:
            self.tabs.setCurrentIndex(index)
            self.omnibox.setFocus()
        return view

    def _show_start_page(self, view: BrowserView) -> None:
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
        if qurl.scheme() == "arkbrowse":
            self.omnibox.setText("")
        else:
            self.omnibox.setText(qurl.toString())
        self._update_security_icon(qurl)

    def _update_security_icon(self, qurl: QUrl) -> None:
        if qurl.scheme() == "arkbrowse":
            self.security_icon.clear()
            self.security_icon.setToolTip("")
        elif qurl.scheme() == "https":
            self.security_icon.setPixmap(self._icon_lock_closed.pixmap(18, 18))
            self.security_icon.setToolTip("Secure connection (HTTPS)")
        else:
            self.security_icon.setPixmap(self._icon_lock_open.pixmap(18, 18))
            self.security_icon.setToolTip("Not secure")

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

    def apply_theme(self) -> None:
        theme_name = self.settings_manager.get("theme_name")
        palette = THEME_PALETTES.get(theme_name, THEME_PALETTES["Obsidian Dark"])
        self.setStyleSheet(build_stylesheet(palette, incognito=self.incognito))
        self._refresh_toolbar_icons()
        apply_windows_titlebar_theme(self, dark=(theme_name != "Classic Light"))

        for i in range(self.tabs.count()):
            view = self.tabs.widget(i)
            if view is not None and view.url().scheme() == "arkbrowse":
                self._show_start_page(view)

    def _refresh_toolbar_icons(self) -> None:
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
            use_https = box.addButton("Use HTTPS", QMessageBox.ButtonRole.AcceptRole)
            continue_http = box.addButton("Continue over HTTP", QMessageBox.ButtonRole.DestructiveRole)
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
        continue_http = box.addButton("Continue over HTTP", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(box.buttons()[-1])
        box.exec()
        if box.clickedButton() is continue_http:
            self.session_policy.allow_http(url)
            return url
        return None

    def closeEvent(self, event) -> None:  # noqa: N802
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

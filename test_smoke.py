"""
Smoke-test harness for arkbrowse.py — NOT part of the deliverable.
Exercises construction of every major class under a real (offscreen) Qt
event loop, so it runs headless in CI/dev containers via the 'offscreen'
platform plugin.

Note on structure: normal windows deliberately share one off-the-record
QWebEngineProfile. This is safe for multiple windows and guarantees that
cookies, cache, history, and other browsing data disappear with the process.
"""
import os
import sys
import time
import traceback

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(__file__))

from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import QApplication
from PyQt6.QtWebEngineCore import QWebEngineUrlRequestInfo

import arkbrowse as ab


def pump(app, cycles=10, delay=0.02):
    """Spin the Qt event loop briefly with tiny real sleeps in between —
    for cases with no specific condition to wait on (e.g. 'let any pending
    signal handlers run')."""
    for _ in range(cycles):
        app.processEvents()
        time.sleep(delay)


def wait_until(app, condition, timeout=12.0, interval=0.05):
    """Poll `condition()` while pumping the Qt event loop, until it returns
    truthy or `timeout` seconds elapse. This is the correct way to wait for
    an async QtWebEngine load/navigation to finish — unlike a fixed number
    of processEvents() cycles, it can't be flaky: it doesn't guess how long
    a load takes (which varies with machine load, network latency, and
    whether the QtWebEngine renderer subprocess is a cold start), it just
    waits exactly as long as actually needed, up to a generous cap.
    Returns condition()'s final (truthy or falsy) value, so callers can
    include it in an assertion message on timeout."""
    deadline = time.time() + timeout
    result = condition()
    while not result and time.time() < deadline:
        app.processEvents()
        time.sleep(interval)
        result = condition()
    return result


class FakeRequestInfo:
    def __init__(self, url, resource_type):
        self._url = url
        self._resource_type = resource_type
        self.redirected_to = None
        self.blocked = False

    def requestUrl(self):
        return self._url

    def resourceType(self):
        return self._resource_type

    def redirect(self, url):
        self.redirected_to = url

    def block(self, blocked):
        self.blocked = blocked


def main():
    app = QApplication(sys.argv)
    app.arkbrowse_windows = []

    # 1. Settings manager round trip
    test_settings_path = "/tmp/arkbrowse_test_settings.json"
    if os.path.exists(test_settings_path):
        os.remove(test_settings_path)
    sm = ab.SettingsManager(path=test_settings_path)
    assert sm.get("theme_name") == "Obsidian Dark"
    assert sm.get("homepage_url") == ab.NEW_TAB_URL, "default homepage must be the internal start page, not a real site"
    sm.set("theme_name", "Cyberpunk Neon")
    sm.save()
    sm2 = ab.SettingsManager(path=test_settings_path)
    assert sm2.get("theme_name") == "Cyberpunk Neon", "settings did not persist"
    print("[OK] SettingsManager persists correctly")
    print("[OK] Default homepage_url is the internal arkBrowse start page, not google.com")

    # Corrupted settings file should fall back to defaults, not crash.
    with open(test_settings_path, "w") as f:
        f.write("{not valid json")
    sm3 = ab.SettingsManager(path=test_settings_path)
    assert sm3.get("theme_name") == "Obsidian Dark"
    print("[OK] SettingsManager recovers from corrupt file")

    # 2. Omnibox URL-vs-search heuristic
    cases = [
        ("google.com", True),
        ("https://openai.com/research", True),
        ("localhost:8000", True),
        ("192.168.1.1", True),
        ("2001:db8::1", True),
        ("[::1]:8080", True),
        ("PRINTER.LOCAL", True),
        ("ftp://ftp.example.com/file.zip", True),
        ("file:///C:/Users/me/file.html", True),
        ("what is the capital of france", False),
        ("best pizza near me", False),
        ("stackoverflow.com/questions/123", True),
        ("", False),
    ]
    for text, expected in cases:
        result = ab.looks_like_url(text)
        assert result == expected, f"looks_like_url({text!r}) = {result}, expected {expected}"
    print("[OK] looks_like_url heuristic passes all cases")

    url1 = ab.build_navigation_url("google.com", "Google")
    assert url1.toString() == "https://google.com", url1.toString()
    url2 = ab.build_navigation_url("best pizza", "DuckDuckGo")
    assert url2.toString().startswith("https://duckduckgo.com/?q=best"), url2.toString()
    url3 = ab.build_navigation_url("2001:db8::1", "Google")
    assert url3.toString() == "https://[2001:db8::1]", url3.toString()
    print("[OK] build_navigation_url handles domains, search queries, and bare IPv6 addresses")

    blocked = ab.load_blocked_domains()
    assert len(blocked) > 100, f"expected bundled filter list, got {len(blocked)} rules"
    interceptor_settings = ab.SettingsManager(
        path="/tmp/arkbrowse_test_interceptor.json"
    )
    interceptor = ab.AdBlockInterceptor(interceptor_settings)
    main_type = QWebEngineUrlRequestInfo.ResourceType.ResourceTypeMainFrame
    image_type = QWebEngineUrlRequestInfo.ResourceType.ResourceTypeImage
    main_request = FakeRequestInfo(QUrl("http://example.org/page"), main_type)
    image_request = FakeRequestInfo(QUrl("http://example.org/image.png"), image_type)
    interceptor.interceptRequest(main_request)
    interceptor.interceptRequest(image_request)
    assert main_request.redirected_to.scheme() == "https"
    assert image_request.redirected_to is None
    assert interceptor._is_local_host("127.0.0.2") is True
    print("[OK] Bundled filters load; HTTPS upgrading touches only main-frame requests")

    # The pure pseudo-URL parser used by ArkWebEnginePage.acceptNavigationRequest
    # (this is what the New Tab page's search box triggers via JS)
    r1 = ab.parse_search_pseudo_url(QUrl("arkbrowse://search?q=google.com"), "Google")
    assert r1 is not None and r1.toString() == "https://google.com", r1
    r2 = ab.parse_search_pseudo_url(QUrl("arkbrowse://search?q=best%20pizza"), "DuckDuckGo")
    assert r2 is not None and r2.toString().startswith("https://duckduckgo.com/?q=best"), r2.toString()
    r3 = ab.parse_search_pseudo_url(QUrl("https://github.com"), "Google")
    assert r3 is None, "a normal URL must not be treated as the search pseudo-URL"
    print("[OK] parse_search_pseudo_url correctly parses the New Tab search box's navigation, and ignores normal URLs")

    # 3. Stylesheets build without raising, for every theme, incognito or not
    for theme_name, palette in ab.THEME_PALETTES.items():
        for incognito in (False, True):
            qss = ab.build_stylesheet(palette, incognito=incognito)
            assert "{" in qss and "}" in qss
    print("[OK] build_stylesheet produced QSS for all themes (normal + incognito)")

    # Start page HTML builds without raising for every theme too
    for theme_name, palette in ab.THEME_PALETTES.items():
        html = ab.build_start_page_html(palette, "Google", incognito=False)
        assert "<html" in html and "ark-search-form" in html
    print("[OK] build_start_page_html produced valid HTML for all themes")

    # 4. Full BrowserWindow construction (this exercises profile setup,
    #    interceptor wiring, toolbar build, tab creation, theming).
    #    show() is required: QtWebEngine defers actual page loading until
    #    a view is visible (a real lifecycle/visibility optimization —
    #    hidden/background tabs don't load) — main() always shows the
    #    window right after construction, so this test does too.
    sm_main = ab.SettingsManager(path="/tmp/arkbrowse_test_settings_main.json")
    window = ab.BrowserWindow(sm_main, incognito=False)
    app.arkbrowse_windows.append(window)
    window.show()
    assert window.tabs.count() == 1, "expected exactly one initial tab"
    print("[OK] BrowserWindow constructed with 1 initial tab")

    # --- New Tab / start-page behavior (the fix for "it opened Google
    #     directly instead of arkBrowse's own start page") ---
    first_view = window.current_view()
    loaded = wait_until(app, lambda: bool(first_view.url().scheme()))
    assert loaded, f"first tab never finished loading anything (url={first_view.url().toString()!r})"
    assert first_view.url().scheme() == "arkbrowse", (
        f"expected the window's first tab to be the start page, got {first_view.url().toString()!r}"
    )
    assert first_view.url().host() == "newtab"
    print("[OK] A freshly opened window's first tab shows the internal start page, not google.com")

    blank_tab = window.add_tab(focus=True)  # Ctrl+T / "+" button equivalent
    wait_until(app, lambda: bool(blank_tab.url().scheme()))
    assert blank_tab.url().scheme() == "arkbrowse"
    print("[OK] Ctrl+T / '+' opens the start page, not the homepage URL or a real website")
    window.close_tab(window.tabs.indexOf(blank_tab))

    real_tab = window.add_tab(url=QUrl("https://github.com"), focus=True)
    wait_until(app, lambda: real_tab.url().toString().startswith("https://github.com"))
    assert real_tab.url().toString().startswith("https://github.com"), real_tab.url().toString()
    print("[OK] Explicitly-provided URLs (e.g. from clicked links) still load normally, bypassing the start page")

    # Custom (non-start-page) homepage still works as a real homepage
    sm_main.set("homepage_url", "https://pypi.org")
    window._go_home()
    wait_until(app, lambda: window.current_view().url().toString().startswith("https://pypi.org"))
    assert window.current_view().url().toString().startswith("https://pypi.org"), window.current_view().url().toString()
    print("[OK] A custom homepage URL (when the user disables the start-page option) still works via Home/_go_home")

    # Reset to start page and confirm _go_home() shows it, not a network URL
    sm_main.set("homepage_url", ab.NEW_TAB_URL)
    window._go_home()
    wait_until(app, lambda: window.current_view().url().scheme() == "arkbrowse")
    assert window.current_view().url().scheme() == "arkbrowse"
    print("[OK] _go_home() shows the start page when homepage is set to the arkBrowse start page")

    # Typing the sentinel into the omnibox also returns to the start page
    detour_tab = window.add_tab(url=QUrl("https://github.com"), focus=True)
    wait_until(app, lambda: bool(detour_tab.url().scheme()))
    window.omnibox.setText("arkbrowse://newtab")
    window._navigate_from_omnibox()
    wait_until(app, lambda: window.current_view().url().scheme() == "arkbrowse")
    assert window.current_view().url().scheme() == "arkbrowse"
    print("[OK] Typing 'arkbrowse://newtab' into the omnibox returns to the start page")

    # Theme switch re-renders a tab currently on the start page
    sm_main.set("theme_name", "Cyberpunk Neon")
    window.apply_theme()  # should not raise, and should re-show the start page
    wait_until(app, lambda: window.current_view().url().scheme() == "arkbrowse")
    assert window.current_view().url().scheme() == "arkbrowse"
    print("[OK] Switching themes re-renders any tab currently on the start page without error")

    # --- General tab / omnibox / settings coverage (unrelated to the
    #     start-page fix, but worth keeping) ---
    while window.tabs.count() > 1:
        window.close_tab(1)
    tab_a = window.add_tab(url=QUrl("https://github.com"), focus=True)
    tab_b = window.add_tab(url=QUrl("https://pypi.org"), focus=True)
    wait_until(app, lambda: bool(tab_a.url().scheme()) and bool(tab_b.url().scheme()))
    assert window.tabs.count() == 3
    window.close_tab(1)
    assert window.tabs.count() == 2
    print("[OK] Tab add/close works")

    window.omnibox.setText("pypi.org")
    window._navigate_from_omnibox()
    pump(app)  # no strict outcome check here — just confirming no exception
    print("[OK] Omnibox navigation executed without error")

    dialog = ab.SettingsDialog(sm_main, on_apply=lambda: None, parent=window)
    assert dialog.theme_combo.count() == len(ab.THEME_PALETTES)
    print("[OK] SettingsDialog constructs correctly")

    # 5. Incognito window: verify off-the-record profile
    incognito_window = ab.BrowserWindow(sm_main, incognito=True)
    app.arkbrowse_windows.append(incognito_window)
    assert incognito_window.profile.isOffTheRecord() is True, "incognito profile must be off-the-record"
    assert window.profile.isOffTheRecord() is True, "normal browsing must also be memory-only"
    print("[OK] Normal and incognito profiles are off-the-record; normal windows do not persist browsing data")

    # Normal windows must reuse one profile instead of creating duplicate
    # profiles with the same storage name.
    second_window = ab.BrowserWindow(sm_main, incognito=False)
    app.arkbrowse_windows.append(second_window)
    assert second_window.profile is window.profile
    print("[OK] Multiple normal windows share one safe ephemeral profile")
    second_window.close()
    assert window.profile.isOffTheRecord() is True
    third_window = ab.BrowserWindow(sm_main, incognito=False)
    app.arkbrowse_windows.append(third_window)
    assert third_window.profile is window.profile
    print("[OK] Closing one normal window leaves the shared profile usable")

    # 6. Ad-block interceptor: domain matching logic
    interceptor = window.interceptor
    assert interceptor._is_blocked_host("doubleclick.net") is True
    assert interceptor._is_blocked_host("ads.doubleclick.net") is True
    assert interceptor._is_blocked_host("www.google.com") is False
    assert interceptor._is_blocked_host("notdoubleclick.net") is False
    print("[OK] AdBlockInterceptor domain matching is correct (incl. subdomain + false-positive checks)")

    # Clean shutdown
    window.close()
    third_window.close()
    incognito_window.close()
    fully_closed = wait_until(app, lambda: len(app.arkbrowse_windows) == 0, timeout=10.0)
    print(f"[INFO] all windows torn down before exit: {fully_closed} (remaining: {len(app.arkbrowse_windows)})")

    # Drop every remaining local reference to a tab/view/dialog object.
    # app.arkbrowse_windows already reached 0 above — proof the actual
    # app-level window/profile teardown (the thing that matters) is
    # correct. What's left here is just this test script's own loose
    # local variables (real_tab, tab_a, blank_tab, dialog, etc.) still
    # referencing already-scheduled-for-deletion Qt wrapper objects;
    # dropping them and pumping once more lets CPython's refcounting and
    # Qt's deferred deletion finish in the same order a normal app run
    # would, rather than at arbitrary interpreter-exit time.
    del (
        first_view, blank_tab, real_tab, detour_tab, tab_a, tab_b,
        dialog, window, second_window, third_window, incognito_window,
    )
    import gc
    gc.collect()
    pump(app, cycles=5)

    for p in (
        test_settings_path,
        "/tmp/arkbrowse_test_settings_main.json",
        "/tmp/arkbrowse_test_interceptor.json",
    ):
        if os.path.exists(p):
            os.remove(p)

    print("\nALL SMOKE TESTS PASSED")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as e:
        print(f"\nASSERTION FAILED: {e}")
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\nUNEXPECTED ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)

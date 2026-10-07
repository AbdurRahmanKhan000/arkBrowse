"""Ad-blocking, HTTPS enforcement, and session policy for arkBrowse."""

from __future__ import annotations

import ipaddress
import re
from PyQt6.QtCore import QUrl
from PyQt6.QtWebEngineCore import QWebEngineUrlRequestInterceptor

from .config import resource_path
from .settings import SettingsManager

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
    """Read host rules from an Adblock/hosts-style filter file."""
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
    """Blocks requests to known ad/tracker domains and upgrades http:// to https://."""

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
            return getattr(resource_type, "name", "") == "ResourceTypeMainFrame"
        except Exception:
            return False

    def interceptRequest(self, info) -> None:  # noqa: N802
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
        except Exception as exc:
            print(f"[arkBrowse] AdBlockInterceptor error: {exc}")

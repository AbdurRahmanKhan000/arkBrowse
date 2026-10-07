"""Start page generation and navigation URL parsing for arkBrowse."""

from __future__ import annotations

import base64
import ipaddress
import re
from urllib.parse import quote_plus
from PyQt6.QtCore import QUrl, QUrlQuery

from .config import (
    INCOGNITO_ACCENT,
    SEARCH_ENGINES,
    resource_path,
)

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
    """Check if omnibox text looks like a URL or domain rather than a search."""
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
    """Turn omnibox text into a QUrl (upgraded address or search query)."""
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
    """Parse arkbrowse://search?q=... pseudo-URL into a target navigation URL."""
    if url.scheme() == "arkbrowse" and url.host() == "search":
        query_text = QUrlQuery(url).queryItemValue(
            "q", QUrl.ComponentFormattingOption.FullyDecoded
        )
        return build_navigation_url(query_text, search_engine)
    return None


_LOGO_BASE64_CACHE: str | None = None


def _logo_base64() -> str:
    """Encode logo.png as base64 for embedding in the start page HTML."""
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
    """Build the HTML for the internal New Tab start page."""
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
  .footer {{
    position: absolute; bottom: 18px; color: {palette['text_dim']}; font-size: 11px;
    letter-spacing: 0.5px; opacity: 0.7; user-select: none;
  }}
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
    <div class="footer">Developed by ARK Ecosystem</div>
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

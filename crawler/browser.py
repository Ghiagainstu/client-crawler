"""Browser-backed fetch for sites protected by bot/WAF (e.g. Akamai).

Uses Playwright Chromium to render the page like a real browser, bypassing
TLS-fingerprint / JS-challenge bot detection that blocks plain ``requests``.
Only used when a client's ``sites.yaml`` sets ``engine: playwright``.

Anti-detection notes
--------------------
Akamai blocks at the TLS/JA3 layer, so we use **patchright** (Playwright's
fingerprint-matched fork) whose Chromium presents the same JA3 as a genuine
Chrome. We also launch with ``--disable-blink-features=AutomationControlled``
and inject a stealth init script to erase ``navigator.webdriver`` et al.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager

log = logging.getLogger("crawler.browser")

# Real desktop Chrome UA — must match a UA a genuine browser would send.
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Erase the automation tells Akamai keys on, before any page script runs.
_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
try { Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] }); } catch (e) {}
try { Object.defineProperty(navigator, 'languages', { get: () => ['en-US','en'] }); } catch (e) {}
try {
  window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){}, app: {} };
} catch (e) {}
"""

_browsers: dict = {}


def _get_browser(proxy: str | None = None, channel: str | None = None):
    from patchright.sync_api import sync_playwright

    key = channel or "bundled"
    global _browsers
    b = _browsers.get(key)
    if b is None or not b.is_connected():
        pw = sync_playwright().start()
        launch_kwargs = {
            "headless": True,
            "args": ["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        }
        if channel:
            # Drive a real installed browser (e.g. "chrome") whose TLS
            # fingerprint matches a genuine client — required to pass Akamai.
            launch_kwargs["channel"] = channel
        if proxy:
            launch_kwargs["proxy"] = {"server": proxy}
        b = pw.chromium.launch(**launch_kwargs)
        _browsers[key] = b
    return b


@contextmanager
def _page(proxy: str | None = None, channel: str | None = None):
    browser = _get_browser(proxy, channel)
    ctx = browser.new_context(
        user_agent=BROWSER_UA,
        viewport={"width": 1366, "height": 768},
        locale="en-US",
    )
    ctx.add_init_script(_STEALTH_JS)
    page = ctx.new_page()
    try:
        yield page
    finally:
        ctx.close()


def fetch(url: str, *, proxy: str | None = None, timeout: int = 30,
          wait: float = 3.0, channel: str | None = None) -> str:
    """Render ``url`` with Chromium and return the resulting HTML string.

    ``wait`` seconds of extra settle time lets Akamai's JS challenge finish
    and the SPA hydrate before we read the DOM. ``channel`` selects a real
    installed browser (e.g. "chrome") instead of the bundled one.
    """
    with _page(proxy, channel) as page:
        page.goto(url, wait_until="load", timeout=timeout * 1000)
        page.wait_for_timeout(int(wait * 1000))
        return page.content()

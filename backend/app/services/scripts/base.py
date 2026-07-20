"""Shared Playwright harness for deterministic 'head-network' scripts.

Extensibility model:
- Each head network provides a small module (entry URLs + selectors + label map + a read/update
  flow) that runs inside browser_session(). Adding a network = one small file, no core changes.
- BOT PROTECTION is a config choice, not code: a network can opt into a residential proxy +
  stealth via env. If a network blocks even that, or is too complex to script, it routes to the
  Skyvern executor instead (which has residential proxies + CAPTCHA + anti-detection built in).
  See services/executor.py for the script-vs-Skyvern routing.
"""
from __future__ import annotations

import os
from contextlib import contextmanager

# Minimal stealth: hide the automation flag most bot-detectors check first.
_STEALTH_JS = (
    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    "window.chrome = window.chrome || {runtime: {}};"
)
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36")


def default_proxy():
    """Residential proxy from env (e.g. BrightData) — None if unset. Networks under bot
    protection set PROXY_SERVER/USER/PASS; the harness routes their traffic through it."""
    server = os.getenv("PROXY_SERVER")
    if not server:
        return None
    return {"server": server, "username": os.getenv("PROXY_USER", ""),
            "password": os.getenv("PROXY_PASS", "")}


@contextmanager
def browser_session(proxy=None, use_default_proxy=False, headless=True):
    """A stealthed Chromium page. Pass a proxy dict, or use_default_proxy=True to pull one from
    env for bot-protected networks. Yields a ready page; always cleans up."""
    from playwright.sync_api import sync_playwright
    if proxy is None and use_default_proxy:
        proxy = default_proxy()
    with sync_playwright() as p:
        launch_kw = {"headless": headless}
        if proxy:
            launch_kw["proxy"] = proxy
        browser = p.chromium.launch(**launch_kw)
        ctx = browser.new_context(user_agent=_UA, viewport={"width": 1440, "height": 900},
                                  locale="en-US")
        ctx.add_init_script(_STEALTH_JS)
        page = ctx.new_page()
        try:
            yield page
        finally:
            browser.close()


def norm(x) -> str:
    return str(x if x is not None else "").strip().lower()

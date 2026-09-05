"""
Browser automation.

This gives EDITH a *controllable* browser — separate from open_website,
which just fires a URL at your regular browser and has no way to reach
back into the page afterward. This one EDITH can read the contents of and
interact with: click things, type into things.

Deliberately general rather than site-specific: instead of hard-coding
selectors for one site (which breaks the moment that site's layout
changes), browser_read_page hands the model a numbered list of visible
interactive elements, and it picks which one to act on by index. That's
less precise than a hand-tuned script for one exact site, but it works
across any page instead of only the one it was written against.

Known limitation: indices are only valid until the page changes — a click
that opens a menu, a navigation, lazily-loaded content. If a click/type
call reports an out-of-range index, the fix is calling browser_read_page
again for fresh indices; the persona is instructed to do this
automatically rather than guessing with stale ones.

Setup: this needs the actual browser binary, not just the Python package:
    pip install playwright
    playwright install chromium
"""

import time

from config import ROOT_DIR, config

_INTERACTIVE_SELECTOR = "button, a, input, textarea, select, [role=button], [contenteditable=true]"
_PROFILE_DIR = ROOT_DIR / "browser_profile"

_playwright = None
_browser_context = None
_page = None


async def _ensure_page():
    global _playwright, _browser_context, _page
    if _page is not None:
        return _page
    from playwright.async_api import async_playwright

    _playwright = await async_playwright().start()
    # A persistent profile (a real folder on disk) instead of a throwaway
    # one — this is what makes logins survive closing the browser or
    # restarting EDITH, the same way your normal Chrome profile does.
    _PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    _browser_context = await _playwright.chromium.launch_persistent_context(
        user_data_dir=str(_PROFILE_DIR),
        headless=config.BROWSER_HEADLESS,
    )
    _page = _browser_context.pages[0] if _browser_context.pages else await _browser_context.new_page()
    return _page


async def browser_navigate(url: str) -> str:
    try:
        page = await _ensure_page()
    except ImportError:
        return "Playwright isn't installed. Run: pip install playwright && playwright install chromium"
    except Exception as exc:  # noqa: BLE001
        return (
            f"Couldn't launch the automated browser ({exc}). If you haven't yet, run: "
            f"playwright install chromium"
        )

    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(500)
        return f"Navigated to {page.url}"
    except Exception as exc:  # noqa: BLE001
        return f"Couldn't navigate to {url}: {exc}"


async def browser_read_page() -> str:
    page = await _ensure_page()
    try:
        elements = await page.eval_on_selector_all(
            _INTERACTIVE_SELECTOR,
            """(els) => els.map((el, i) => {
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) return null;
                const label = (el.innerText || el.value || el.placeholder ||
                    el.getAttribute('aria-label') || '').trim().replace(/\\s+/g, ' ').slice(0, 60);
                return { index: i, tag: el.tagName.toLowerCase(), label };
            }).filter(Boolean).slice(0, 60)""",
        )
    except Exception as exc:  # noqa: BLE001
        return f"Couldn't read the page: {exc}"

    if not elements:
        return "No interactive elements found on the current page."
    lines = [f"[{e['index']}] <{e['tag']}> {e['label']}" for e in elements]
    return "Interactive elements on the current page:\n" + "\n".join(lines)


async def browser_click(index: int) -> str:
    page = await _ensure_page()
    elements = await page.query_selector_all(_INTERACTIVE_SELECTOR)
    if index < 0 or index >= len(elements):
        return f"No element at index {index}. Call browser_read_page again for current indices."
    try:
        await elements[index].click(timeout=5000)
        await page.wait_for_timeout(300)
        return f"Clicked element [{index}]."
    except Exception as exc:  # noqa: BLE001
        return f"Couldn't click element [{index}]: {exc}"


async def browser_type(index: int, text: str) -> str:
    page = await _ensure_page()
    elements = await page.query_selector_all(_INTERACTIVE_SELECTOR)
    if index < 0 or index >= len(elements):
        return f"No element at index {index}. Call browser_read_page again for current indices."
    try:
        # Click first, then type via the keyboard rather than setting a
        # value directly — this is what makes it work on rich editors like
        # Monaco/CodeMirror (LeetCode, etc.) that capture real keystrokes
        # instead of reading an input's .value.
        await elements[index].click(timeout=5000)
        await page.keyboard.type(text, delay=15)
        return f"Typed into element [{index}]."
    except Exception as exc:  # noqa: BLE001
        return f"Couldn't type into element [{index}]: {exc}"


async def browser_screenshot() -> str:
    page = await _ensure_page()
    path = config.SCREENSHOT_DIR / f"browser_{int(time.time())}.png"
    try:
        await page.screenshot(path=str(path))
        return f"Browser screenshot saved to {path}"
    except Exception as exc:  # noqa: BLE001
        return f"Couldn't take screenshot: {exc}"


async def browser_close() -> str:
    global _playwright, _browser_context, _page
    try:
        if _browser_context:
            await _browser_context.close()
        if _playwright:
            await _playwright.stop()
    finally:
        _playwright = None
        _browser_context = None
        _page = None
    return "Closed the automated browser."
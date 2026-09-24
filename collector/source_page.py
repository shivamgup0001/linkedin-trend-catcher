"""Shared navigation and candidate-loading behavior for discovery sources."""

from urllib.parse import urlsplit

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


WORKSPACE_SELECTOR = "main#workspace"


def is_authentication_page(url):
    parts = urlsplit(url)
    if (parts.hostname or "").casefold() not in {"linkedin.com", "www.linkedin.com"}:
        return False
    path = parts.path.casefold()
    return (
        path == "/login"
        or path.startswith("/login/")
        or path == "/checkpoint"
        or path.startswith("/checkpoint/")
    )


def navigate_to_source(
    page,
    url,
    workspace_timeout_ms=None,
    allow_missing_workspace=False,
    fallback_workspace_selector=None,
):
    """Navigate once, detect authentication redirects, and await the workspace."""
    page.goto(url, wait_until="domcontentloaded")
    if is_authentication_page(page.url):
        raise RuntimeError("LinkedIn session expired; log in again before collecting")

    wait_options = {}
    if workspace_timeout_ms is not None:
        wait_options["timeout"] = workspace_timeout_ms
    try:
        page.wait_for_selector(WORKSPACE_SELECTOR, **wait_options)
    except PlaywrightTimeoutError:
        if is_authentication_page(page.url):
            raise RuntimeError("LinkedIn session expired; log in again before collecting")
        if fallback_workspace_selector:
            try:
                if page.locator(fallback_workspace_selector).count() > 0:
                    return True
            except (AttributeError, TypeError):
                pass
        if allow_missing_workspace:
            return False
        raise
    return True


def load_scrolled_candidates(
    page,
    scroller,
    collector,
    skip_scroll_when_empty=False,
):
    """Use the shared scroller and candidate locator after source navigation."""
    if skip_scroll_when_empty:
        candidates = collector.get_post_candidates(page)
        if candidates.count() == 0:
            return candidates
    scroller.scroll(page)
    return collector.get_post_candidates(page)

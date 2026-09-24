"""Shared navigation and candidate-loading behavior for discovery sources."""

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from collector.session import (
    is_authentication_page,
    require_authenticated_page,
    require_safe_response,
)


WORKSPACE_SELECTOR = "main#workspace"


def navigate_to_source(
    page,
    url,
    workspace_timeout_ms=None,
    allow_missing_workspace=False,
    fallback_workspace_selector=None,
):
    """Navigate once, detect authentication redirects, and await the workspace."""
    response = page.goto(url, wait_until="domcontentloaded")
    require_safe_response(response)
    require_authenticated_page(page)

    wait_options = {}
    if workspace_timeout_ms is not None:
        wait_options["timeout"] = workspace_timeout_ms
    try:
        page.wait_for_selector(WORKSPACE_SELECTOR, **wait_options)
    except PlaywrightTimeoutError:
        require_authenticated_page(page)
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

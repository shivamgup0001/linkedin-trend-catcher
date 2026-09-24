"""LinkedIn session detection shared by authentication and collectors."""

from urllib.parse import urlsplit


AUTHENTICATION_PATHS = (
    "/authwall",
    "/checkpoint",
    "/login",
    "/signup",
    "/uas/login",
)
LOGGED_OUT_SELECTORS = (
    "input#username",
    "input#password",
    "form[action*='/login']",
    "a[href*='/login'][data-tracking-control-name]",
)


class LinkedInSafetyStop(RuntimeError):
    """Base error for conditions that must stop all collection immediately."""


class LinkedInAuthenticationError(LinkedInSafetyStop):
    """Raised when LinkedIn requires login or presents an account checkpoint."""


class LinkedInRateLimitError(LinkedInSafetyStop):
    """Raised when LinkedIn explicitly rate-limits a request."""


def is_authentication_page(url):
    parts = urlsplit(str(url or ""))
    if (parts.hostname or "").casefold() not in {"linkedin.com", "www.linkedin.com"}:
        return False
    path = parts.path.casefold().rstrip("/") or "/"
    return any(
        path == prefix or path.startswith(prefix + "/")
        for prefix in AUTHENTICATION_PATHS
    )


def has_logged_out_layout(page):
    """Detect login controls when LinkedIn leaves the URL looking authenticated."""
    for selector in LOGGED_OUT_SELECTORS:
        try:
            if page.locator(selector).count() > 0:
                return True
        except (AttributeError, TypeError):
            continue
    return False


def require_authenticated_page(page):
    if is_authentication_page(page.url) or has_logged_out_layout(page):
        raise LinkedInAuthenticationError(
            "LinkedIn session expired or was challenged; log in again before collecting"
        )


def require_safe_response(response):
    if response is not None and response.status == 429:
        raise LinkedInRateLimitError(
            "LinkedIn returned HTTP 429; stop collection and wait before retrying"
        )

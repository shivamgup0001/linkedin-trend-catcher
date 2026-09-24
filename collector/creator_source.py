from urllib.parse import urlsplit, urlunsplit

from playwright.sync_api import Locator, Page

from collector.collector import LinkedInCollector
from collector.scroller import LinkedInScroller
from collector.source_page import (
    is_authentication_page,
    load_scrolled_candidates,
    navigate_to_source,
)
from config.discovery_source import DiscoverySource, DiscoverySourceType


class CreatorSourceCollector:
    """Load post candidates from a creator's LinkedIn activity page."""

    WORKSPACE_SELECTOR = "main#workspace"
    WORKSPACE_TIMEOUT_MS = 10000

    def __init__(self, scroller=None, collector=None):
        self.scroller = scroller or LinkedInScroller()
        self.collector = collector or LinkedInCollector()
        self.last_status = "not_run"

    def load_candidates(self, page: Page, source: DiscoverySource) -> Locator:
        """Navigate to ``source`` activity and return its unparsed post candidates."""
        self.last_status = "loading"
        self._validate_source(source)
        workspace_loaded = navigate_to_source(
            page,
            self._activity_url(source.url),
            workspace_timeout_ms=self.WORKSPACE_TIMEOUT_MS,
            allow_missing_workspace=True,
            fallback_workspace_selector="main",
        )
        if not workspace_loaded:
            self.last_status = "workspace_missing"
            return self.collector.get_post_candidates(page)
        candidates = load_scrolled_candidates(page, self.scroller, self.collector)
        self.last_status = "ok"
        return candidates

    @staticmethod
    def _validate_source(source: DiscoverySource) -> None:
        if getattr(source, "source_type", None) != DiscoverySourceType.CREATOR:
            raise ValueError("CreatorSourceCollector requires a CREATOR source")
        if not getattr(source, "url", None):
            raise ValueError("Creator source requires a profile URL")

    @staticmethod
    def _activity_url(profile_url: str) -> str:
        parts = urlsplit(profile_url)
        segments = [segment for segment in parts.path.split("/") if segment]
        hostname = (parts.hostname or "").casefold()
        if (
            parts.scheme.casefold() not in {"http", "https"}
            or hostname not in {"linkedin.com", "www.linkedin.com"}
            or len(segments) != 2
            or segments[0].casefold() != "in"
        ):
            raise ValueError("Creator source requires a LinkedIn /in/.../ profile URL")

        path = f"/in/{segments[1]}/recent-activity/all/"
        return urlunsplit(("https", "www.linkedin.com", path, "", ""))

    @staticmethod
    def _is_authentication_page(url: str) -> bool:
        return is_authentication_page(url)

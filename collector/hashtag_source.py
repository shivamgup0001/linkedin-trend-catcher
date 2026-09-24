from urllib.parse import urlencode, urlunsplit

from playwright.sync_api import Locator, Page, TimeoutError as PlaywrightTimeoutError

from collector.collector import LinkedInCollector
from collector.scroller import LinkedInScroller
from collector.source_page import load_scrolled_candidates, navigate_to_source
from config.discovery_source import DiscoverySource, DiscoverySourceType


class HashtagSourceCollector:
    """Navigate a LinkedIn hashtag content search and return its candidates."""

    SEARCH_PATH = "/search/results/content/"
    RESULTS_TIMEOUT_MS = 10000

    def __init__(self, scroller=None, collector=None):
        self.scroller = scroller or LinkedInScroller()
        self.collector = collector or LinkedInCollector()

    def load_candidates(
        self, page: Page, source: DiscoverySource, candidate_limit=None
    ) -> Locator:
        if (
            not isinstance(source, DiscoverySource)
            or source.source_type != DiscoverySourceType.HASHTAG
        ):
            raise ValueError("HashtagSourceCollector requires a HASHTAG discovery source")

        hashtag = source.value.strip().lstrip("#")
        if not hashtag:
            raise ValueError("Hashtag discovery source cannot be empty")

        query = urlencode({"keywords": f"#{hashtag}"})
        url = urlunsplit(("https", "www.linkedin.com", self.SEARCH_PATH, query, ""))
        navigate_to_source(page, url)
        workspace = page.locator("main#workspace")
        try:
            workspace.get_by_role("listitem").first.wait_for(
                timeout=self.RESULTS_TIMEOUT_MS
            )
        except PlaywrightTimeoutError:
            pass

        return load_scrolled_candidates(
            page,
            self.scroller,
            self.collector,
            skip_scroll_when_empty=True,
            candidate_limit=candidate_limit,
        )

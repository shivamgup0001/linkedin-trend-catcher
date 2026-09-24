from playwright.sync_api import Page, Locator

class LinkedInCollector:
    """
    Responsible for locating all LinkedIn posts on the page
    """

    FEED_SELECTOR = "main#workspace"

    def get_post_candidates(self, page: Page) -> Locator:
        """
        Returns all post locators from the LinkedIn search results page.
        """
        feed_posts = page.locator(".feed-shared-update-v2")
        if feed_posts.count() > 0:
            return feed_posts
        return page.locator(self.FEED_SELECTOR).get_by_role("listitem")

    @staticmethod
    def is_post_candidate(candidate: Locator) -> bool:
        """Reject navigation and recommendation list items mixed into search results."""
        try:
            menu = candidate.get_by_role(
                "button", name="Open control menu for post", exact=False
            )
            if menu.count() > 0:
                return True
        except Exception:
            pass

        selectors = (
            '[data-testid="expandable-text-box"]',
            '[data-urn*="urn:li:activity"]',
            '[data-urn*="urn:li:ugcPost"]',
            'a[href*="/feed/update/"]',
            'a[href*="/posts/"]',
            'a[href*="/pulse/"]',
        )
        for selector in selectors:
            try:
                if candidate.locator(selector).count() > 0:
                    return True
            except Exception:
                continue
        return False

    def first_post_candidate(self, candidates: Locator):
        for index in range(candidates.count()):
            candidate = candidates.nth(index)
            if self.is_post_candidate(candidate):
                return candidate
        return None

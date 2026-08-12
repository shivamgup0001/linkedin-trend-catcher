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
        return page.locator(self.FEED_SELECTOR).get_by_role("listitem")
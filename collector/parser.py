from playwright.sync_api import Locator
from models.post import Post
import re

class LinkedInParser:

    def parse(self, post: Locator):

        return Post(
            activity_id=self._get_activity_id(post),
            author=self._get_author(post),
            author_url=self._get_author_url(post),
            text=self._get_text(post),
        )

    def _get_activity_id(self, post):
        # TODO:
        # LinkedIn search results do not consistently expose the activity URN.
        # We'll revisit this when parsing the dedicated post page.
        
        return None

    def _get_author(self, post: Locator):
        try:
            links = post.locator('a[href*="/in/"]')

            for i in range(links.count()):
                text = links.nth(i).text_content()

                if text and text.strip():
                    return text.split("•")[0].strip()

            return None

        except Exception:
            return None

    def _get_author_url(self, post: Locator):
        try:
            links = post.locator('a[href*="/in/"]')

            for i in range(links.count()):
                href = links.nth(i).get_attribute("href")

                if href:
                    return href

            return None

        except Exception:
            return None

    def _get_text(self, post: Locator):
        try:
            text = post.locator('[data-testid="expandable-text-box"]').text_content()
            return text.strip() if text else ""
        except Exception:
            return None
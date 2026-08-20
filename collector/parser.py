from playwright.sync_api import Locator
from models.post import Post
import re
from urllib.parse import unquote

class LinkedInParser:

    def parse(self, post: Locator, keyword: str):

        media_type = self._get_media_type(post)
        return Post(
            keyword = keyword,
            activity_id=self._get_activity_id(post),
            author=self._get_author(post),
            author_url=self._get_author_url(post),
            text=self._get_text(post),
            posted_at=self._get_posted_at(post),
            likes=self._get_likes(post),
            comments=self._get_comments(post),
            reposts=self._get_reposts(post),
            has_image=(media_type == "image"),
            has_video=(media_type == "video"),
            post_url=self._get_post_url(post),
        )

    def _get_activity_id(self, post):
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

    def _get_posted_at(self, post: Locator):
        text = post.text_content() or ""

        match = re.search(r"\d+(?:s|m|h|d|w|mo|y)", text)

        if match:
            return match.group(0)

        return None

    def _get_likes(self, post: Locator):
        try:
            links = post.get_by_role("link")

            for i in range(links.count()):
                text = (links.nth(i).text_content() or "").strip()

                if "reaction" in text.lower():
                    match = re.search(r"(\d+)\s+reactions?", text)

                    if match:
                        return int(match.group(1))

            return None

        except Exception:
            return None

    def _get_reposts(self, post: Locator):
        try:
            links = post.get_by_role("link")

            for i in range(links.count()):
                text = (links.nth(i).text_content() or "").strip()

                if "repost" in text.lower():
                    match = re.search(r"(\d+)", text)

                    if match:
                        return int(match.group(1))

            return 0

        except Exception:
            return 0

    def _get_comments(self, post: Locator):
        try:
            buttons = post.get_by_role("button")

            for i in range(buttons.count()):
                text = (buttons.nth(i).text_content() or "").strip()

                if "comment" in text.lower():
                    match = re.search(r"(\d+)", text)

                    if match:
                        return int(match.group(1))

            return 0

        except Exception:
            return 0

    def _get_media_type(self, post: Locator):

        if post.locator("video").count() > 0:
            return "video"

        # Uploaded image(s)
        images = post.locator("img")

        for i in range(images.count()):
            alt = images.nth(i).get_attribute("alt") or ""

            if alt == "View image":
                return "image"
        
        # TODO:
        # Detect article preview
        # Detect carousel
        # Detect document/PDF
        # Detect poll

        return None

    def _get_post_url(self, post: Locator):
        """
        TODO:
        Search results do not expose the canonical LinkedIn post URL.
        Implement after activity_id extraction or via a different endpoint.
        """
        return None
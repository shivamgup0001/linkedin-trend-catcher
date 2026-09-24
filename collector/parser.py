from playwright.sync_api import Locator, Page
from models.post import Post
import html
import re
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

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
        url = self._get_post_url(post)
        if url:
            activity_id = self._extract_activity_id(url)
            if activity_id:
                return activity_id

        candidates = [post, post.locator("[data-urn], [data-id]")]
        for candidate in candidates:
            for index in range(candidate.count()):
                for attribute in ("data-urn", "data-id"):
                    value = candidate.nth(index).get_attribute(attribute) or ""
                    match = re.search(r"urn:li:(?:activity|ugcPost):(\d+)", value)
                    if match:
                        return match.group(1)

        try:
            markup = unquote(html.unescape(post.evaluate("element => element.outerHTML")))
            match = re.search(
                r"(?:urn:li:(?:activity|ugcPost):|liveVideoUpdateReplaceableSlot:)(\d{10,})",
                markup,
            )
            if match:
                return match.group(1)
        except Exception:
            pass
        return None

    @staticmethod
    def _extract_activity_id(value):
        match = re.search(r"(?:urn:li:(?:activity|ugcPost):|(?:activity|ugcPost)-)(\d+)", value)
        return match.group(1) if match else None

    def resolve_post_url_from_menu(self, page: Page, post: Locator):
        original_clipboard = None
        try:
            original_clipboard = page.evaluate("navigator.clipboard.readText()")
            page.evaluate("navigator.clipboard.writeText('')")
            menu_button = post.get_by_role("button", name="Open control menu for post", exact=False)
            if menu_button.count() == 0:
                return None
            post.scroll_into_view_if_needed(timeout=2000)
            page.wait_for_timeout(200)
            menu_button.first.click(timeout=2000)
            copy_item = page.get_by_role("menuitem", name="Copy link to post", exact=False)
            copy_item.first.wait_for(state="visible", timeout=3000)
            copy_item.first.click(timeout=2000)
            page.wait_for_timeout(100)
            url = page.evaluate("navigator.clipboard.readText()")
            return self._normalize_post_url(url)
        except Exception:
            return None
        finally:
            page.keyboard.press("Escape")
            if original_clipboard is not None:
                try:
                    page.evaluate("text => navigator.clipboard.writeText(text)", original_clipboard)
                except Exception:
                    pass

    def _get_author(self, post: Locator):
        try:
            links = self._get_author_links(post)

            for i in range(links.count()):
                text = links.nth(i).text_content()

                if text and text.strip():
                    return text.split("•")[0].strip()

            return None

        except Exception:
            return None

    def _get_author_url(self, post: Locator):
        try:
            links = self._get_author_links(post)

            for i in range(links.count()):
                href = links.nth(i).get_attribute("href")

                if href:
                    return href

            return None

        except Exception:
            return None

    def _get_text(self, post: Locator):
        try:
            text_box = post.locator('[data-testid="expandable-text-box"]')
            if text_box.count() == 0:
                return None
            text = text_box.first.text_content(timeout=2000)
            return text.strip() if text else ""
        except Exception:
            return None

    def _get_posted_at(self, post: Locator):
        text = post.text_content() or ""

        match = re.search(r"\d+(?:mo|s|m|h|d|w|y)", text)

        if match:
            return match.group(0)

        return None

    def _get_likes(self, post: Locator):
        return self._get_metric(post, "reaction", default=0)

    def _get_reposts(self, post: Locator):
        return self._get_metric(post, "repost", default=0)

    def _get_comments(self, post: Locator):
        return self._get_metric(post, "comment", default=0)

    def _get_metric(self, post: Locator, noun: str, default):
        try:
            saw_metric_label = False
            for role in ("link", "button"):
                elements = post.get_by_role(role)
                for index in range(elements.count()):
                    element = elements.nth(index)
                    values = (
                        element.text_content() or "",
                        element.get_attribute("aria-label") or "",
                    )
                    for value in values:
                        if noun not in value.lower():
                            continue
                        saw_metric_label = True
                        count = self._parse_metric_count(value, noun)
                        if count is not None:
                            return count
            return None if saw_metric_label else default
        except Exception:
            return default

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

    @staticmethod
    def _parse_metric_count(text, noun):
        match = re.search(
            rf"(\d[\d,]*(?:\.\d+)?\s*[KMB]?)\s*{noun}s?",
            text,
            re.IGNORECASE,
        )
        if not match:
            match = re.search(
                rf"{noun}s?\s*(\d[\d,]*(?:\.\d+)?\s*[KMB]?)",
                text,
                re.IGNORECASE,
            )
        if not match:
            return None

        value = match.group(1).replace(",", "").replace(" ", "")
        multiplier = 1
        if value[-1:].upper() in {"K", "M", "B"}:
            multiplier = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[value[-1].upper()]
            value = value[:-1]
        return int(float(value) * multiplier)

    def _get_post_url(self, post: Locator):
        """
        Returns the canonical LinkedIn URL when it is exposed.

        Supports:
        - Feed posts
        - UGC posts
        - Pulse articles
        - Group posts (via highlightedUpdateUrn)

        Returns None if no canonical URL is available.
        """

        links = post.locator("a")

        for i in range(links.count()):

            try:
                href = links.nth(i).get_attribute("href")

                if not href:
                    continue

                if "/feed/update/" in href:
                    return self._normalize_post_url(urljoin("https://www.linkedin.com", href))

                if "/posts/" in href:
                    return self._normalize_post_url(urljoin("https://www.linkedin.com", href))

                if "/pulse/" in href:
                    return self._normalize_post_url(urljoin("https://www.linkedin.com", href))

                match = re.search(r"highlightedUpdateUrn=(urn:li:(?:activity|ugcPost):\d+)", unquote(href))

                if match:
                    urn = match.group(1)
                    return f"https://www.linkedin.com/feed/update/{urn}/"

            except Exception:
                continue

        return None

    @staticmethod
    def _get_author_links(post: Locator):
        return post.locator(
            'a[href*="/in/"], a[href*="/company/"], a[href*="/school/"]'
        )

    @staticmethod
    def _normalize_post_url(value):
        if not value:
            return None
        try:
            parts = urlsplit(value.strip())
            hostname = (parts.hostname or "").lower()
            if hostname != "linkedin.com" and not hostname.endswith(".linkedin.com"):
                return None
            path = parts.path.rstrip("/") + "/"
            return urlunsplit(("https", "www.linkedin.com", path, "", ""))
        except Exception:
            return None

    def _print_all_links(self, post):

        links = post.locator("a")

        print(f"\nFound {links.count()} links\n")

        for i in range(links.count()):

            href = links.nth(i).get_attribute("href")

            if href:
                print(href)

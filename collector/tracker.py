from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from collector.collector import LinkedInCollector
from collector.session import require_authenticated_page, require_safe_response


class LinkedInTracker:
    def __init__(self, parser):
        self.parser = parser

    def refresh(self, page, target):
        response = page.goto(target["post_url"], wait_until="domcontentloaded")
        require_safe_response(response)
        require_authenticated_page(page)

        if response is not None and response.status >= 400:
            return {
                "status": "http_error",
                "detail": f"LinkedIn returned HTTP {response.status}",
            }

        try:
            page.wait_for_selector("main#workspace", timeout=10000)
        except PlaywrightTimeoutError:
            require_authenticated_page(page)
            return {
                "status": "workspace_missing",
                "detail": f"Post workspace did not load; final URL: {page.url}",
            }

        collector = LinkedInCollector()
        candidates = collector.get_post_candidates(page)
        post = collector.first_post_candidate(candidates)
        if post is None:
            return {
                "status": "unsupported_layout",
                "detail": f"No post container found; final URL: {page.url}",
            }

        return {
            "status": "ok",
            "post_id": target["post_id"],
            "likes": self.parser._get_likes(post),
            "comments": self.parser._get_comments(post),
            "reposts": self.parser._get_reposts(post),
        }

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from collector.collector import LinkedInCollector


class LinkedInTracker:
    def __init__(self, parser):
        self.parser = parser

    def refresh(self, page, target):
        response = page.goto(target["post_url"], wait_until="domcontentloaded")
        if "/login" in page.url or "/checkpoint/" in page.url:
            raise RuntimeError("LinkedIn session expired; log in again before collecting")

        if response is not None and response.status >= 400:
            return {
                "status": "http_error",
                "detail": f"LinkedIn returned HTTP {response.status}",
            }

        try:
            page.wait_for_selector("main#workspace", timeout=10000)
        except PlaywrightTimeoutError:
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

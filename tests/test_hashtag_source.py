import unittest
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from collector.hashtag_source import HashtagSourceCollector
from config.discovery_source import DiscoverySource, DiscoverySourceType


class HashtagSourceCollectorTests(unittest.TestCase):
    def setUp(self):
        self.page = MagicMock()
        self.page.url = "https://www.linkedin.com/search/results/content/"
        self.workspace = self.page.locator.return_value
        self.scroller = MagicMock()
        self.collector = MagicMock()
        self.source_collector = HashtagSourceCollector(
            scroller=self.scroller,
            collector=self.collector,
        )

    def test_constructs_encoded_hashtag_content_search_url(self):
        candidates = MagicMock()
        candidates.count.return_value = 1
        self.collector.get_post_candidates.return_value = candidates
        source = DiscoverySource(DiscoverySourceType.HASHTAG, "#AgenticAI")

        self.source_collector.load_candidates(self.page, source)

        url = self.page.goto.call_args.args[0]
        parsed = urlsplit(url)
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "www.linkedin.com")
        self.assertEqual(parsed.path, "/search/results/content/")
        self.assertEqual(parse_qs(parsed.query), {"keywords": ["#AgenticAI"]})
        self.assertIn("keywords=%23AgenticAI", url)
        self.assertEqual(
            self.page.goto.call_args.kwargs,
            {"wait_until": "domcontentloaded"},
        )

    def test_rejects_non_hashtag_source_before_navigation(self):
        source = DiscoverySource(DiscoverySourceType.KEYWORD, "AI")

        with self.assertRaisesRegex(ValueError, "HASHTAG"):
            self.source_collector.load_candidates(self.page, source)

        self.page.goto.assert_not_called()

    def test_detects_login_and_checkpoint_redirects(self):
        source = DiscoverySource(DiscoverySourceType.HASHTAG, "AI")
        redirect_urls = (
            "https://www.linkedin.com/login?fromSignIn=true",
            "https://www.linkedin.com/checkpoint/challenge/123",
        )

        for redirect_url in redirect_urls:
            with self.subTest(redirect_url=redirect_url):
                page = MagicMock()
                page.url = redirect_url
                with self.assertRaisesRegex(RuntimeError, "session expired"):
                    self.source_collector.load_candidates(page, source)
                page.wait_for_selector.assert_not_called()

    def test_waits_scrolls_and_returns_candidates(self):
        candidates = MagicMock()
        candidates.count.return_value = 2
        self.collector.get_post_candidates.return_value = candidates
        source = DiscoverySource(DiscoverySourceType.HASHTAG, "AI")

        result = self.source_collector.load_candidates(self.page, source)

        self.page.wait_for_selector.assert_called_once_with("main#workspace")
        self.workspace.get_by_role.assert_called_once_with("listitem")
        self.workspace.get_by_role.return_value.first.wait_for.assert_called_once_with(
            timeout=10000
        )
        self.scroller.scroll.assert_called_once_with(self.page)
        self.assertIs(result, candidates)
        self.collector.get_post_candidates.assert_called_once_with(self.page)

    def test_zero_results_returns_empty_locator_without_scrolling(self):
        self.workspace.get_by_role.return_value.first.wait_for.side_effect = (
            PlaywrightTimeoutError("no hashtag results")
        )
        empty_candidates = MagicMock()
        empty_candidates.count.return_value = 0
        self.collector.get_post_candidates.return_value = empty_candidates
        source = DiscoverySource(DiscoverySourceType.HASHTAG, "NoResultsExpected")

        result = self.source_collector.load_candidates(self.page, source)

        self.assertIs(result, empty_candidates)
        self.scroller.scroll.assert_not_called()
        self.collector.get_post_candidates.assert_called_once_with(self.page)


if __name__ == "__main__":
    unittest.main()

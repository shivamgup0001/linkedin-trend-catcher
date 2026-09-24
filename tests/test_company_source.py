import unittest
from unittest.mock import Mock

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from collector.company_source import CompanySourceCollector
from config.discovery_source import DiscoverySource, DiscoverySourceType


class CompanySourceCollectorTests(unittest.TestCase):
    def setUp(self):
        self.page = Mock()
        self.page.url = "https://www.linkedin.com/company/example/posts/?feedView=all"
        self.scroller = Mock()
        self.candidate_collector = Mock()
        self.candidates = Mock(name="candidates")
        self.candidate_collector.get_post_candidates.return_value = self.candidates
        self.collector = CompanySourceCollector(
            scroller=self.scroller,
            collector=self.candidate_collector,
        )
        self.source = DiscoverySource(
            DiscoverySourceType.COMPANY,
            "Example",
            name="Example",
            url="https://www.linkedin.com/company/example/",
        )

    def test_generates_deterministic_company_posts_url(self):
        source = DiscoverySource(
            DiscoverySourceType.COMPANY,
            "Example",
            name="Example",
            url="http://linkedin.com/company/example/?trk=organization#about",
        )

        self.collector.load_candidates(self.page, source)

        self.page.goto.assert_called_once_with(
            "https://www.linkedin.com/company/example/posts/?feedView=all",
            wait_until="domcontentloaded",
        )

    def test_rejects_non_company_source(self):
        source = DiscoverySource(DiscoverySourceType.KEYWORD, "Example")

        with self.assertRaisesRegex(ValueError, "COMPANY"):
            self.collector.load_candidates(self.page, source)

        self.page.goto.assert_not_called()

    def test_rejects_company_without_page_url(self):
        source = DiscoverySource(DiscoverySourceType.COMPANY, "Example")

        with self.assertRaisesRegex(ValueError, "page URL"):
            self.collector.load_candidates(self.page, source)

        self.page.goto.assert_not_called()

    def test_detects_login_and_checkpoint_redirects(self):
        expired_urls = (
            "https://www.linkedin.com/login?fromSignIn=true",
            "https://www.linkedin.com/checkpoint/challenge/123/",
        )
        for expired_url in expired_urls:
            with self.subTest(url=expired_url):
                self.page.reset_mock()
                self.page.url = expired_url
                with self.assertRaisesRegex(RuntimeError, "session expired"):
                    self.collector.load_candidates(self.page, self.source)
                self.page.wait_for_selector.assert_not_called()
                self.scroller.scroll.assert_not_called()

    def test_returns_candidates_after_waiting_and_scrolling(self):
        result = self.collector.load_candidates(self.page, self.source)

        self.page.wait_for_selector.assert_called_once_with(
            "main#workspace",
            timeout=10000,
        )
        self.scroller.scroll.assert_called_once_with(self.page)
        self.candidate_collector.get_post_candidates.assert_called_once_with(self.page)
        self.assertIs(result, self.candidates)

    def test_empty_page_returns_empty_candidates(self):
        self.candidates.count.return_value = 0

        result = self.collector.load_candidates(self.page, self.source)

        self.assertEqual(result.count(), 0)
        self.scroller.scroll.assert_called_once_with(self.page)

    def test_unsupported_page_returns_empty_locator_without_scrolling(self):
        self.page.wait_for_selector.side_effect = PlaywrightTimeoutError(
            "workspace not found"
        )
        self.candidates.count.return_value = 0

        result = self.collector.load_candidates(self.page, self.source)

        self.assertEqual(result.count(), 0)
        self.scroller.scroll.assert_not_called()
        self.candidate_collector.get_post_candidates.assert_called_once_with(self.page)


if __name__ == "__main__":
    unittest.main()

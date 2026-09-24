import unittest
from unittest.mock import Mock

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from collector.creator_source import CreatorSourceCollector
from config.discovery_source import DiscoverySource, DiscoverySourceType


class CreatorSourceCollectorTests(unittest.TestCase):
    def setUp(self):
        self.scroller = Mock()
        self.candidate_collector = Mock()
        self.collector = CreatorSourceCollector(
            scroller=self.scroller,
            collector=self.candidate_collector,
        )

    @staticmethod
    def creator(url="https://www.linkedin.com/in/jane-doe/"):
        return DiscoverySource(
            DiscoverySourceType.CREATOR,
            "Jane Doe",
            name="Jane Doe",
            url=url,
        )

    def test_profile_url_is_normalized_to_recent_activity(self):
        page = Mock()
        page.url = "https://www.linkedin.com/in/jane-doe/recent-activity/all/"
        candidates = Mock()
        candidates.count.return_value = 1
        self.candidate_collector.get_post_candidates.return_value = candidates

        result = self.collector.load_candidates(
            page,
            self.creator("http://linkedin.com/in/jane-doe/?trk=profile#about"),
        )

        page.goto.assert_called_once_with(
            "https://www.linkedin.com/in/jane-doe/recent-activity/all/",
            wait_until="domcontentloaded",
        )
        page.wait_for_selector.assert_called_once_with(
            "main#workspace", timeout=10000
        )
        self.scroller.scroll.assert_called_once_with(page)
        self.assertIs(result, candidates)

    def test_non_creator_sources_are_rejected_before_navigation(self):
        page = Mock()
        source = DiscoverySource(
            DiscoverySourceType.COMPANY,
            "Example",
            name="Example",
            url="https://www.linkedin.com/company/example/",
        )

        with self.assertRaisesRegex(ValueError, "CREATOR"):
            self.collector.load_candidates(page, source)

        page.goto.assert_not_called()

    def test_creator_without_profile_url_is_rejected(self):
        page = Mock()
        with self.assertRaisesRegex(ValueError, "profile URL"):
            self.collector.load_candidates(
                page,
                DiscoverySource(DiscoverySourceType.CREATOR, "Jane Doe"),
            )

    def test_login_and_checkpoint_redirects_report_session_expiry(self):
        for redirected_url in (
            "https://www.linkedin.com/login?fromSignIn=true",
            "https://www.linkedin.com/checkpoint/challenge/123",
        ):
            with self.subTest(url=redirected_url):
                page = Mock()
                page.url = redirected_url

                with self.assertRaisesRegex(RuntimeError, "session expired"):
                    self.collector.load_candidates(page, self.creator())

        self.scroller.scroll.assert_not_called()
        self.candidate_collector.get_post_candidates.assert_not_called()

    def test_returns_candidates_after_scrolling(self):
        page = Mock()
        page.url = "https://www.linkedin.com/in/jane-doe/recent-activity/all/"
        candidates = Mock()
        self.candidate_collector.get_post_candidates.return_value = candidates

        self.assertIs(self.collector.load_candidates(page, self.creator()), candidates)

        self.scroller.scroll.assert_called_once_with(page)
        self.candidate_collector.get_post_candidates.assert_called_once_with(page)

    def test_empty_activity_page_returns_empty_candidates(self):
        page = Mock()
        page.url = "https://www.linkedin.com/in/jane-doe/recent-activity/all/"
        empty_candidates = Mock()
        empty_candidates.count.return_value = 0
        self.candidate_collector.get_post_candidates.return_value = empty_candidates

        result = self.collector.load_candidates(page, self.creator())

        self.assertEqual(result.count(), 0)
        self.scroller.scroll.assert_called_once_with(page)

    def test_missing_workspace_is_treated_as_an_unsupported_empty_layout(self):
        page = Mock()
        page.url = "https://www.linkedin.com/in/jane-doe/recent-activity/all/"
        page.wait_for_selector.side_effect = PlaywrightTimeoutError("not found")
        empty_candidates = Mock()
        empty_candidates.count.return_value = 0
        self.candidate_collector.get_post_candidates.return_value = empty_candidates

        result = self.collector.load_candidates(page, self.creator())

        self.assertEqual(result.count(), 0)
        self.scroller.scroll.assert_not_called()

    def test_plain_main_fallback_supports_current_activity_layout(self):
        page = Mock()
        page.url = "https://www.linkedin.com/in/jane-doe/recent-activity/all/"
        page.wait_for_selector.side_effect = PlaywrightTimeoutError("no workspace id")
        page.locator.side_effect = lambda selector: Mock(
            **{"count.return_value": 1 if selector == "main" else 0}
        )
        candidates = Mock()
        self.candidate_collector.get_post_candidates.return_value = candidates

        result = self.collector.load_candidates(page, self.creator())

        page.locator.assert_any_call("main")
        self.scroller.scroll.assert_called_once_with(page)
        self.assertIs(result, candidates)
        self.assertEqual(self.collector.last_status, "ok")


if __name__ == "__main__":
    unittest.main()

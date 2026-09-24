import unittest
from unittest.mock import Mock

from collector.session import (
    LinkedInAuthenticationError,
    LinkedInRateLimitError,
    has_logged_out_layout,
    is_authentication_page,
    require_authenticated_page,
    require_safe_response,
)


class LinkedInSessionTests(unittest.TestCase):
    def test_authentication_urls_include_login_signup_checkpoint_and_authwall(self):
        for url in (
            "https://www.linkedin.com/login",
            "https://www.linkedin.com/signup/cold-join",
            "https://www.linkedin.com/checkpoint/challenge/123",
            "https://www.linkedin.com/authwall?trk=bf",
            "https://www.linkedin.com/uas/login",
        ):
            with self.subTest(url=url):
                self.assertTrue(is_authentication_page(url))

        self.assertFalse(is_authentication_page("https://www.linkedin.com/feed/"))
        self.assertFalse(is_authentication_page("https://example.com/login"))

    def test_logged_out_controls_are_detected_on_feed_url(self):
        page = Mock()
        page.url = "https://www.linkedin.com/feed/"
        page.locator.return_value.count.return_value = 1

        self.assertTrue(has_logged_out_layout(page))
        with self.assertRaises(LinkedInAuthenticationError):
            require_authenticated_page(page)

    def test_authenticated_page_is_accepted(self):
        page = Mock()
        page.url = "https://www.linkedin.com/feed/"
        page.locator.return_value.count.return_value = 0

        require_authenticated_page(page)

    def test_http_429_stops_collection(self):
        response = Mock(status=429)

        with self.assertRaisesRegex(LinkedInRateLimitError, "HTTP 429"):
            require_safe_response(response)

        require_safe_response(Mock(status=200))


if __name__ == "__main__":
    unittest.main()

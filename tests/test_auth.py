import unittest
from unittest.mock import Mock, patch

from collector.auth import LINKEDIN_FEED, LinkedInAuth
from collector.session import LinkedInAuthenticationError


def fake_playwright(final_url):
    page = Mock()
    page.url = final_url
    page.locator.return_value.count.return_value = 0
    context = Mock()
    context.new_page.return_value = page
    browser = Mock()
    browser.new_context.return_value = context
    playwright = Mock()
    playwright.chromium.launch.return_value = browser
    return playwright, browser, context, page


class LinkedInAuthTests(unittest.TestCase):
    @patch("collector.auth.SESSION_FILE")
    def test_saved_session_is_verified_before_context_is_returned(self, session_file):
        session_file.exists.return_value = True
        playwright, browser, context, page = fake_playwright(LINKEDIN_FEED)

        result = LinkedInAuth(playwright, headless=True).get_authenticated_context()

        self.assertIs(result, context)
        browser.new_context.assert_called_once_with(storage_state=session_file)
        page.goto.assert_called_once_with(LINKEDIN_FEED, wait_until="domcontentloaded")
        page.wait_for_selector.assert_called_once_with("main#workspace", timeout=10000)
        page.close.assert_called_once()
        context.close.assert_not_called()

    @patch("collector.auth.SESSION_FILE")
    def test_expired_saved_session_closes_browser_and_fails_fast(self, session_file):
        session_file.exists.return_value = True
        playwright, browser, context, page = fake_playwright(
            "https://www.linkedin.com/signup/cold-join"
        )

        with self.assertRaises(LinkedInAuthenticationError):
            LinkedInAuth(playwright, headless=True).get_authenticated_context()

        page.close.assert_called_once()
        context.close.assert_called_once()
        browser.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()

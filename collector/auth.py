from pathlib import Path
from playwright.sync_api import BrowserContext, Playwright, TimeoutError as PlaywrightTimeoutError

from collector.session import (
    LinkedInAuthenticationError,
    require_authenticated_page,
    require_safe_response,
)

# Where we'll store the logged-in session
SESSION_DIR = Path("data/auth")
SESSION_FILE = SESSION_DIR / "linkedin_state.json"

LINKEDIN_FEED = "https://www.linkedin.com/feed/"
WORKSPACE_SELECTOR = "main#workspace"

class LinkedInAuth:
    """
    Handles LinkedIn authentication.

    Responsibilities:
    1. Reuse an existing logged-in session if available.
    2. Otherwise allow a one-time manual login.
    3. Save the logged-in session for future use.
    """

    def __init__(self, playwright:Playwright, headless: bool = False):
        self.playwright = playwright
        self.headless = headless    

    def get_authenticated_context(self) -> BrowserContext:
        """
        Returns an authenticated browser context.
        """

        SESSION_DIR.mkdir(parents=True, exist_ok=True)

        browser = self.playwright.chromium.launch(headless=self.headless)

        # ------------------
        # Existing session
        # ------------------
        if SESSION_FILE.exists():
            print("Reusing existing logged-in session...")
            context = browser.new_context(storage_state=SESSION_FILE)
            try:
                self._validate_context(context)
            except Exception:
                context.close()
                browser.close()
                raise
            return context

        # ------------------
        # First-time login
        # ------------------
        print("\nNo LinkedIn session found.")
        print("A browser window will open.")
        print("Please log into LinkedIn manually.\n")

        context = browser.new_context()

        page = context.new_page()

        page.goto(LINKEDIN_FEED)

        input("Press Enter after logging in to LinkedIn...")

        try:
            response = page.goto(LINKEDIN_FEED, wait_until="domcontentloaded")
            require_safe_response(response)
            self._validate_page(page)
        except Exception:
            context.close()
            browser.close()
            raise

        context.storage_state(path=str(SESSION_FILE))

        print(f"\n Session saved to {SESSION_FILE}")

        return context

    def _validate_context(self, context):
        page = context.new_page()
        try:
            response = page.goto(LINKEDIN_FEED, wait_until="domcontentloaded")
            require_safe_response(response)
            self._validate_page(page)
        finally:
            page.close()

    @staticmethod
    def _validate_page(page):
        require_authenticated_page(page)
        try:
            page.wait_for_selector(WORKSPACE_SELECTOR, timeout=10000)
        except PlaywrightTimeoutError as error:
            require_authenticated_page(page)
            raise LinkedInAuthenticationError(
                "LinkedIn session could not be verified; log in again before collecting"
            ) from error

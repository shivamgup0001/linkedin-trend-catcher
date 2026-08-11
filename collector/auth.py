from pathlib import Path
from playwright.sync_api import BrowserContext, Playwright

# Where we'll store the logged-in session
SESSION_DIR = Path("data/auth")
SESSION_FILE = SESSION_DIR / "linkedin_state.json"

LINKEDIN_FEED = "https://www.linkedin.com/feed/"

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

            return browser.new_context(storage_state=SESSION_FILE)

        # ------------------
        # First-time login
        # ------------------
        print("\nNo LinkedIn session found.")
        print("A browser window will open.")
        print("Please log into LinkedIn manuallly.\n")

        context = browser.new_context()

        page = context.new_page()

        page.goto(LINKEDIN_FEED)

        input("Press Enter after logging in to LinkedIn...")

        context.storage_state(path=str(SESSION_FILE))

        print(f"\n Session saved to {SESSION_FILE}")

        return context
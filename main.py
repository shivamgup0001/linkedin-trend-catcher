from playwright.sync_api import sync_playwright

from config.config_loader import load_keywords
from collector.auth import LinkedInAuth
from collector.search import LinkedInSearch
from collector.scroller import LinkedInScroller

def main():
    keywords = load_keywords()

    with sync_playwright() as playwright:
        auth = LinkedInAuth(playwright)

        context = auth.get_authenticated_context()

        searcher = LinkedInSearch()

        scroller = LinkedInScroller()

        for keyword in keywords:

            page = context.new_page()

            print(f"Searching: {keyword}")

            searcher.search(page, keyword)

            scroller.scroll(page)

            input("Check search results and then press Enter...")

            page.close()

        context.close()

if __name__ == "__main__":
    main()
        # Add your processing logic here
from playwright.sync_api import sync_playwright

from config.config_loader import load_keywords
from collector.auth import LinkedInAuth
from collector.search import LinkedInSearch
from collector.scroller import LinkedInScroller
from collector.collector import LinkedInCollector
from collector.parser import LinkedInParser
from collector.interceptor import NetworkInterceptor


def main():
    keywords = load_keywords()

    with sync_playwright() as playwright:
        auth = LinkedInAuth(playwright)

        context = auth.get_authenticated_context()

        searcher = LinkedInSearch()

        scroller = LinkedInScroller()

        collector = LinkedInCollector()

        parser = LinkedInParser()

        for keyword in keywords:

            page = context.new_page()

            interceptor = NetworkInterceptor()
            page.on("response", interceptor.handle_response)

            print(f"Searching: {keyword}")

            searcher.search(page, keyword)

            scroller.scroll(page)

            # Let any remaining network requests finish
            page.wait_for_timeout(3000)

            posts = collector.get_post_candidates(page)

            print(f"Found {posts.count()} posts")

            print(parser.parse(posts.nth(0)))

            input("Press Enter to continue...")

            page.close()

        context.close()

if __name__ == "__main__":
    main()
        # Add your processing logic here
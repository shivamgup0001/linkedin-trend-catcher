from playwright.sync_api import sync_playwright

from config.config_loader import load_keywords
from collector.auth import LinkedInAuth
from collector.search import LinkedInSearch
from collector.scroller import LinkedInScroller
from collector.collector import LinkedInCollector
from collector.parser import LinkedInParser
from collector.interceptor import NetworkInterceptor

from database.mongo import MongoDB

from analytics.trend_analyzer import TrendAnalyzer
from analytics.report_printer import ReportPrinter

def main():
    keywords = load_keywords()

    db = MongoDB()

    analyzer = TrendAnalyzer(db.collection)

    printer = ReportPrinter()

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

            for i in range(posts.count()):

                try:
                    post = parser.parse(posts.nth(i), keyword)
                    db.save_post(post)

                except Exception as e:
                    print(f"Failed on post {i+1}: {e}")

            input("Press Enter to continue...")

            page.close()

        context.close()

    report = analyzer.generate_report()

    printer.print(report)

if __name__ == "__main__":
    main()
        # Add your processing logic here
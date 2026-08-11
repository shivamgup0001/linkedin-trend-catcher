from urllib.parse import quote

class LinkedInSearch:

    BASE_URL = "https://www.linkedin.com/search/results/content/?keywords={}"

    def search(self, page, keyword):
        url = self.BASE_URL.format(quote(keyword))

        page.goto(url, wait_until="domcontentloaded")

        # Wait for the main content area
        page.wait_for_selector("main")

        return page
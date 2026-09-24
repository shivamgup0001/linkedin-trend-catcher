from urllib.parse import quote

from collector.source_page import navigate_to_source

class LinkedInSearch:

    BASE_URL = "https://www.linkedin.com/search/results/content/?keywords={}"

    def search(self, page, keyword):
        url = self.BASE_URL.format(quote(keyword))

        navigate_to_source(page, url)
        try:
            page.locator("main#workspace").get_by_role("listitem").first.wait_for(timeout=10000)
        except Exception:
            # The page may legitimately contain no results; the collector will report zero.
            pass

        return page

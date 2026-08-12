from playwright.sync_api import Page

class LinkedInScroller:
    """
    Responsible only for loading more content by scrolling
    """

    def scroll(self, page: Page, max_scrolls: int =1):
        previous_height = 0

        for i in range(max_scrolls):
            # Get the current height of the page
            previous_height = page.evaluate("""
                () => {
                    const container = document.querySelector("main#workspace");
                    return container.scrollHeight;
                }
            """)

            # Scroll down to the bottom of the page
            page.evaluate("""
                () => {
                    const container = document.querySelector("main#workspace");
                    container.scrollTo(0, container.scrollHeight);
                }
            """)

            # Wait for new content to load
            page.wait_for_timeout(2000)  # Wait for 2 seconds

            # Check if the page grew
            new_height = ("""
                () => {
                    const container = document.querySelector("main#workspace");
                    return container.scrollHeight;
                }
            """)

            print(f"Scroll {i+1}: {new_height} (previous: {previous_height})")

            if new_height == previous_height:
                print("Reached end of loaded content.")
                break

            previous_height = new_height
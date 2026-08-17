import re


class NetworkInterceptor:

    def __init__(self):
        self.activity_ids = []

    def handle_response(self, response):
        if "pagination?" not in response.url:
            return

        try:
            text = response.body().decode("utf-8", errors="ignore")

            ids = list(dict.fromkeys(
                re.findall(r"urn:li:activity:(\d+)", text)
            ))

            for activity_id in ids:
                if activity_id not in self.activity_ids:
                    self.activity_ids.append(activity_id)

        except Exception:
            pass
import unittest
from datetime import datetime, timedelta, timezone

from analytics.growth import growth_between
from analytics.trend_analyzer import TrendAnalyzer
from collector.collector import LinkedInCollector
from collector.parser import LinkedInParser
from database.mongo import MongoDB
from models.post import Post


class FakeLocator:
    def __init__(self, attributes=None, children=None, markup="", roles=None, text=""):
        self.attributes = attributes or {}
        self.children = children or {}
        self.markup = markup
        self.roles = roles or {}
        self.text = text

    def locator(self, selector):
        return FakeGroup(self.children.get(selector, []))

    def count(self):
        return 1

    def nth(self, index):
        return self

    def get_attribute(self, name):
        return self.attributes.get(name)

    def text_content(self, **kwargs):
        return self.text

    def evaluate(self, expression):
        return self.markup

    def get_by_role(self, role, **kwargs):
        return FakeGroup(self.roles.get(role, []))


class FakeGroup:
    def __init__(self, items):
        self.items = items

    def count(self):
        return len(self.items)

    def nth(self, index):
        return self.items[index]


class FakeDocuments:
    def __init__(self, documents):
        self.documents = documents

    def find(self, query=None):
        query = query or {}
        return [document for document in self.documents if self._matches(document, query)]

    def find_one(self, query, sort=None):
        matches = self.find(query)
        if sort:
            field, direction = sort[0]
            matches.sort(key=lambda item: item[field], reverse=direction < 0)
        return matches[0] if matches else None

    @staticmethod
    def _matches(document, query):
        for field, expected in query.items():
            actual = document.get(field)
            if isinstance(expected, dict):
                if "$lte" in expected and not actual <= expected["$lte"]:
                    return False
            elif actual != expected:
                return False
        return True


class TrackingTests(unittest.TestCase):
    def test_growth_uses_elapsed_time_and_skips_unknown_metrics(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        before = {"observed_at": start, "likes": 10, "comments": None, "reposts": 2}
        after = {"observed_at": start + timedelta(hours=2), "likes": 30, "comments": 8, "reposts": 4}
        growth = growth_between(before, after)
        self.assertEqual(growth["changes"], {"likes": 20, "comments": None, "reposts": 2})
        self.assertEqual(growth["score_components"], {"likes": 20, "comments": 0, "reposts": 10})
        self.assertEqual(growth["weighted_growth"], 30)
        self.assertEqual(growth["score_per_hour"], 15)

    def test_trending_uses_an_eligible_baseline_instead_of_too_recent_snapshot(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        current_time = start + timedelta(hours=2)
        snapshots = FakeDocuments([
            {"post_id": "post-1", "observed_at": start, "likes": 10, "comments": 0, "reposts": 0},
            {"post_id": "post-1", "observed_at": start + timedelta(hours=1.5), "likes": 25, "comments": 0, "reposts": 0},
            {"post_id": "post-1", "observed_at": current_time, "likes": 30, "comments": 0, "reposts": 0},
        ])
        posts = FakeDocuments([{
            "post_id": "post-1",
            "author": "Jane",
            "keyword": "SaaS",
            "post_url": "https://www.linkedin.com/posts/example/",
            "posted_at": "2h",
        }])

        ranked = TrendAnalyzer(posts, snapshots).top_trending(
            current_time,
            min_window_hours=1,
            min_growth=3,
        )

        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0]["previous_observed_at"], start)
        self.assertEqual(ranked[0]["weighted_growth"], 20)
        self.assertEqual(ranked[0]["score_per_hour"], 10)

    def test_engagement_reports_use_latest_snapshots(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        posts = FakeDocuments([
            {"post_id": "post-1", "author": "Jane", "keyword": "SaaS"},
            {"post_id": "post-2", "author": "Alex", "keyword": "SaaS"},
        ])
        snapshots = FakeDocuments([
            {"post_id": "post-1", "observed_at": start, "likes": 2, "comments": 1, "reposts": 0},
            {"post_id": "post-1", "observed_at": start + timedelta(hours=1), "likes": 20, "comments": 3, "reposts": 1},
            {"post_id": "post-2", "observed_at": start, "likes": 10, "comments": 1, "reposts": 0},
        ])
        analyzer = TrendAnalyzer(posts, snapshots)

        self.assertEqual(
            analyzer.average_metrics(),
            {"avg_likes": 15.0, "avg_comments": 2.0, "avg_reposts": 0.5},
        )
        top = analyzer.top_engagement_posts(limit=1)
        self.assertEqual(top[0]["author"], "Jane")
        self.assertEqual(top[0]["score"], 34)

    def test_activity_id_from_encoded_highlighted_urn(self):
        link = FakeLocator({"href": "/groups/123/?highlightedUpdateUrn=urn%3Ali%3Aactivity%3A456"})
        post = FakeLocator(children={"a": [link]})
        parser = LinkedInParser()
        self.assertEqual(parser._get_activity_id(post), "456")
        self.assertEqual(parser._get_post_url(post), "https://www.linkedin.com/feed/update/urn:li:activity:456/")

    def test_activity_id_from_nested_data_urn(self):
        nested = FakeLocator({"data-urn": "urn:li:activity:789"})
        post = FakeLocator(children={"[data-urn], [data-id]": [nested]})
        self.assertEqual(LinkedInParser()._get_activity_id(post), "789")

    def test_activity_id_from_hidden_live_video_slot(self):
        post = FakeLocator(markup='<div id="liveVideoUpdateReplaceableSlot:7504159106090459136"></div>')
        self.assertEqual(LinkedInParser()._get_activity_id(post), "7504159106090459136")

    def test_activity_id_from_shared_post_url(self):
        url = "https://www.linkedin.com/posts/example_topic-ugcPost-7507786211072065536-abcd/"
        self.assertEqual(LinkedInParser._extract_activity_id(url), "7507786211072065536")

    def test_content_fingerprint_is_stable_across_formatting(self):
        first = Post(keyword="AI", author="Jane", text="Hello   world")
        second = Post(keyword="Agents", author="jane", text="Hello\nworld")
        first_id, first_source = MongoDB._get_post_id(first)
        second_id, second_source = MongoDB._get_post_id(second)
        self.assertEqual(first_id, second_id)
        self.assertEqual(first_source, "content_fingerprint")
        self.assertEqual(second_source, "content_fingerprint")

    def test_compact_and_comma_metric_counts(self):
        parser = LinkedInParser()
        self.assertEqual(parser._parse_metric_count("1,234 reactions", "reaction"), 1234)
        self.assertEqual(parser._parse_metric_count("2.5K comments", "comment"), 2500)
        self.assertEqual(parser._parse_metric_count("469 reactions469", "reaction"), 469)
        self.assertEqual(parser._parse_metric_count("Reactions 3.2K", "reaction"), 3200)

    def test_post_url_normalization_removes_tracking_data(self):
        url = "https://www.linkedin.com/posts/example-activity-123-abcd?utm_source=share#detail"
        self.assertEqual(
            LinkedInParser._normalize_post_url(url),
            "https://www.linkedin.com/posts/example-activity-123-abcd/",
        )
        self.assertIsNone(LinkedInParser._normalize_post_url("https://example.com/post"))

    def test_missing_reaction_counter_is_zero_but_malformed_label_is_unknown(self):
        parser = LinkedInParser()
        self.assertEqual(parser._get_likes(FakeLocator()), 0)
        malformed = FakeLocator(
            roles={
                "button": [FakeLocator(attributes={"aria-label": "Many reactions"})]
            }
        )
        self.assertIsNone(parser._get_likes(malformed))

    def test_company_pages_are_supported_as_authors(self):
        company = FakeLocator(
            attributes={"href": "https://www.linkedin.com/company/example/"},
            text="Example Company • 10K followers",
        )
        post = FakeLocator(
            children={
                'a[href*="/in/"], a[href*="/company/"], a[href*="/school/"]': [company]
            }
        )
        parser = LinkedInParser()
        self.assertEqual(parser._get_author(post), "Example Company")
        self.assertEqual(
            parser._get_author_url(post),
            "https://www.linkedin.com/company/example/",
        )

    def test_candidate_validation_rejects_unrelated_list_items(self):
        unrelated = FakeLocator()
        post = FakeLocator(
            roles={"button": [FakeLocator()]},
        )
        self.assertFalse(LinkedInCollector.is_post_candidate(unrelated))
        self.assertTrue(LinkedInCollector.is_post_candidate(post))

    def test_post_age_understands_months(self):
        observed = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(TrendAnalyzer._post_age_hours({"posted_at": "2mo"}, observed), 1440)


if __name__ == "__main__":
    unittest.main()

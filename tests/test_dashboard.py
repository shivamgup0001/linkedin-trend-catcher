import unittest
from datetime import datetime, timedelta, timezone

from dashboard_data import (
    DashboardDataAccess,
    build_collection_run_rows,
    build_overview,
    build_post_selector_options,
    build_trend_rows,
    filter_trend_rows,
    latest_snapshot,
    rank_trend_rows,
)


class FakeCollection:
    def __init__(self, documents):
        self.documents = list(documents)

    def find(self, query=None):
        query = query or {}
        return [
            document for document in self.documents
            if all(document.get(key) == value for key, value in query.items())
        ]

    def find_one(self, query):
        matches = self.find(query)
        return matches[0] if matches else None


class DashboardDataTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def test_latest_snapshot_ignores_order_and_missing_timestamp(self):
        newest = {"post_id": "one", "observed_at": self.start + timedelta(hours=3)}
        result = latest_snapshot([
            newest,
            {"post_id": "one"},
            {"post_id": "one", "observed_at": self.start},
        ])
        self.assertIs(result, newest)
        self.assertIsNone(latest_snapshot([{"post_id": "one"}]))

    def test_post_selector_options_are_newest_first_and_readable(self):
        options = build_post_selector_options([
            {
                "post_id": "older",
                "author": "Ada",
                "text": "An older post",
                "last_seen_at": self.start,
            },
            {
                "post_id": "newer",
                "author": "Grace",
                "text": "A newer post with   normalized spacing",
                "last_seen_at": self.start + timedelta(hours=1),
            },
            {"author": "Missing identity"},
        ])

        self.assertEqual([item["post_id"] for item in options], ["newer", "older"])
        self.assertEqual(
            options[0]["label"],
            "Grace | A newer post with normalized spacing",
        )

    def test_post_selector_uses_identity_when_text_is_missing(self):
        options = build_post_selector_options([{"post_id": "activity:123"}])

        self.assertEqual(options[0]["label"], "Unknown author | activity:123")

    def test_trend_rows_use_latest_snapshot_and_eligible_baseline(self):
        posts = [{
            "post_id": "one",
            "author": "Ada",
            "keyword": "AI",
            "posted_at": "2h",
            "last_seen_at": self.start + timedelta(hours=1),
            "post_url": "https://www.linkedin.com/posts/one/",
            "last_refresh_status": "ok",
        }]
        snapshots = [
            {"post_id": "one", "observed_at": self.start + timedelta(hours=3),
             "likes": 20, "comments": 4, "reposts": 2},
            {"post_id": "one", "observed_at": self.start,
             "likes": 10, "comments": 1, "reposts": 0},
            {"post_id": "one", "observed_at": self.start + timedelta(hours=2.5),
             "likes": 19, "comments": 4, "reposts": 2},
        ]

        rows = build_trend_rows(posts, snapshots, min_window_hours=1)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["baseline_observation"], self.start)
        self.assertEqual(row["last_observation"], self.start + timedelta(hours=3))
        self.assertEqual(row["reactions"], 20)
        self.assertEqual(row["reaction_growth"], 10)
        self.assertEqual(row["comment_growth"], 3)
        self.assertEqual(row["repost_growth"], 2)
        self.assertEqual(row["weighted_growth"], 29)
        self.assertEqual(row["score_per_hour"], 9.67)
        self.assertEqual(row["momentum_score"], 2.42)
        self.assertEqual(row["breakout_score"], 72.5)
        self.assertEqual(row["confidence"], "low")
        self.assertEqual(row["snapshot_count"], 3)
        self.assertEqual(row["effective_hours"], 6)
        self.assertEqual(row["post_age_hours"], 4)

    def test_short_windows_are_dampened_in_momentum_ranking(self):
        short = {
            "post_id": "short",
            "momentum_score": 1.0,
            "breakout_score": 20.0,
            "weighted_growth": 12,
            "score_per_hour": 12,
        }
        sustained = {
            "post_id": "sustained",
            "momentum_score": 3.0,
            "breakout_score": 10.0,
            "weighted_growth": 48,
            "score_per_hour": 4,
        }

        ranked = rank_trend_rows([short, sustained], "momentum")

        self.assertEqual([row["post_id"] for row in ranked], ["sustained", "short"])

    def test_breakout_ranking_is_independent_from_momentum(self):
        established = {
            "post_id": "established", "momentum_score": 8,
            "breakout_score": 12, "weighted_growth": 80,
        }
        emerging = {
            "post_id": "emerging", "momentum_score": 4,
            "breakout_score": 60, "weighted_growth": 40,
        }

        self.assertEqual(
            rank_trend_rows([established, emerging], "momentum")[0]["post_id"],
            "established",
        )
        self.assertEqual(
            rank_trend_rows([established, emerging], "breakout")[0]["post_id"],
            "emerging",
        )

    def test_unknown_ranking_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported trend ranking"):
            rank_trend_rows([], "viral")

    def test_filtering_combines_all_dashboard_filters(self):
        matching = {
            "post_id": "one", "author": "Ada", "keyword": "AI",
            "weighted_growth": 12, "post_age_hours": 24, "refresh_status": "ok",
        }
        rows = [
            matching,
            {**matching, "post_id": "two", "keyword": "SaaS"},
            {**matching, "post_id": "three", "author": "Grace"},
            {**matching, "post_id": "four", "weighted_growth": 2},
            {**matching, "post_id": "five", "post_age_hours": 200},
            {**matching, "post_id": "six", "refresh_status": "http_error"},
            {**matching, "post_id": "seven", "post_age_hours": None},
        ]

        filtered = filter_trend_rows(
            rows,
            keywords=["AI"],
            authors=["Ada"],
            min_growth=3,
            max_post_age_days=7,
            statuses=["ok"],
        )

        self.assertEqual(filtered, [matching])

    def test_empty_data_returns_zero_overview_and_no_trends(self):
        overview = build_overview([], [])

        self.assertEqual(overview["total_posts"], 0)
        self.assertEqual(overview["directly_refreshable"], 0)
        self.assertEqual(overview["posts_with_two_snapshots"], 0)
        self.assertEqual(overview["failed_refreshes"], 0)
        self.assertIsNone(overview["latest_snapshot_time"])
        self.assertEqual(overview["keywords"], [])
        self.assertEqual(build_trend_rows([], []), [])

    def test_overview_and_detail_use_snapshot_history(self):
        posts = [
            {"post_id": "one", "keyword": "AI",
             "post_url": "https://www.linkedin.com/feed/update/urn:li:activity:1/",
             "last_refresh_status": "ok"},
            {"post_id": "two", "keyword": "SaaS",
             "post_url": "https://www.linkedin.com/posts/two/",
             "tracking_enabled": False, "last_refresh_status": "http_error"},
            {"post_id": "three", "keyword": "AI"},
        ]
        snapshots = [
            {"post_id": "one", "observed_at": self.start + timedelta(hours=1)},
            {"post_id": "one", "observed_at": self.start},
            {"post_id": "two", "observed_at": self.start + timedelta(hours=2)},
        ]
        overview = build_overview(posts, snapshots)

        self.assertEqual(overview["directly_refreshable"], 1)
        self.assertEqual(overview["posts_with_two_snapshots"], 1)
        self.assertEqual(overview["failed_refreshes"], 1)
        self.assertEqual(overview["keywords"], ["AI", "SaaS"])
        self.assertEqual(overview["latest_snapshot_time"], self.start + timedelta(hours=2))

        access = DashboardDataAccess(FakeCollection(posts), FakeCollection(snapshots))
        post, history = access.post_detail("one")
        self.assertEqual(post["keyword"], "AI")
        self.assertEqual(history[0]["observed_at"], self.start)
        self.assertEqual(history[1]["observed_at"], self.start + timedelta(hours=1))

    def test_missing_fields_do_not_create_a_trend(self):
        snapshots = [
            {"post_id": "one", "observed_at": self.start},
            {"post_id": "one", "observed_at": self.start + timedelta(hours=2)},
        ]
        self.assertEqual(build_trend_rows([{"post_id": "one"}], snapshots), [])

    def test_naive_and_aware_snapshot_times_are_supported(self):
        snapshots = [
            {"post_id": "one", "observed_at": self.start.replace(tzinfo=None),
             "likes": 1, "comments": 0, "reposts": 0},
            {"post_id": "one", "observed_at": self.start + timedelta(hours=2),
             "likes": 3, "comments": 0, "reposts": 0},
        ]
        rows = build_trend_rows([{"post_id": "one", "first_seen_at": self.start}], snapshots)
        self.assertEqual(rows[0]["weighted_growth"], 2)

    def test_collection_runs_connect_diagnostics_to_dashboard(self):
        older = {
            "run_id": "older",
            "mode": "discover",
            "status": "completed",
            "started_at": self.start,
            "active_discovery_sources": [{"type": "keyword", "value": "SaaS"}],
            "discovery": {"candidates_found": 10, "valid_posts_found": 8,
                          "posts_saved": 8, "canonical_urls_resolved": 7,
                          "skips_by_reason": {"not_post": 2}},
            "refresh": {},
        }
        newer = {
            "run_id": "newer",
            "mode": "all",
            "status": "partial",
            "started_at": self.start + timedelta(hours=1),
            "discovery": {"quality_warnings_by_reason": {"missing_author": 1}},
            "refresh": {"attempts": 5, "successes": 4, "failures": 1},
            "error_count": 1,
            "errors": [{"stage": "refresh", "message": "unsupported layout"}],
        }

        access = DashboardDataAccess(
            FakeCollection([]), FakeCollection([]), FakeCollection([older, newer])
        )
        rows = build_collection_run_rows(access.load_collection_runs())

        self.assertEqual([row["run_id"] for row in rows], ["newer", "older"])
        self.assertEqual(rows[0]["refresh_successes"], 4)
        self.assertEqual(rows[0]["quality_warnings"], 1)
        self.assertEqual(rows[1]["active_sources"], "keyword: SaaS")
        self.assertEqual(rows[1]["skips"], 2)


if __name__ == "__main__":
    unittest.main()

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from config.discovery_source import DiscoverySource, DiscoverySourceType
from dashboard_data import (
    build_source_health_rows,
    build_trend_rows,
    filter_trend_rows,
    normalized_discovery_sources,
)
from main import discover_posts, parse_args, refresh_posts
from collector.session import LinkedInAuthenticationError
from collector.source_adapter import build_source_adapters
from models.collection_run import CollectionRunDiagnostics
from models.post import Post


class FakeCount:
    def __init__(self, count):
        self.value = count

    def count(self):
        return self.value


class FakeCandidate:
    def get_by_role(self, role, **kwargs):
        return FakeCount(1)


class FakeCandidates:
    def __init__(self, count):
        self.items = [FakeCandidate() for _ in range(count)]

    def count(self):
        return len(self.items)

    def nth(self, index):
        return self.items[index]


class FakeAdapter:
    def __init__(self, candidate_count=0, error=None):
        self.candidate_count = candidate_count
        self.error = error
        self.calls = []

    def load_candidates(self, page, source):
        self.calls.append((page, source))
        if self.error:
            raise self.error
        return FakeCandidates(self.candidate_count)


class FakePage:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True

    def wait_for_timeout(self, milliseconds):
        pass


class FakeContext:
    def __init__(self):
        self.pages = []

    def new_page(self):
        page = FakePage()
        self.pages.append(page)
        return page


class FakeParser:
    def __init__(self, canonical_url=None):
        self.canonical_url = canonical_url
        self.parsed_sources = []

    def parse(self, candidate, source_value):
        self.parsed_sources.append(source_value)
        return Post(
            keyword=source_value,
            activity_id="123",
            author="Ada",
            text="Shared post",
            likes=4,
            comments=1,
            reposts=0,
            post_url="https://www.linkedin.com/feed/update/urn:li:activity:123/",
        )

    def resolve_post_url_from_menu(self, page, candidate):
        return self.canonical_url

    @staticmethod
    def _extract_activity_id(url):
        return "123"


class FakeDB:
    def __init__(self):
        self.observations = []

    def save_observation(self, post, observed_at, source):
        self.observations.append((post, observed_at, source))
        return True

    def refresh_targets(self, max_track_days, refresh_limit):
        return [
            {"post_id": "one", "post_url": "https://www.linkedin.com/posts/one/"},
            {"post_id": "two", "post_url": "https://www.linkedin.com/posts/two/"},
        ]

    def save_refresh_failure(self, *args):
        raise AssertionError("Authentication failure must not be stored as a post failure")


def source(source_type, value):
    if source_type == DiscoverySourceType.CREATOR:
        return DiscoverySource(
            source_type,
            value,
            name=value,
            url="https://www.linkedin.com/in/example/",
        )
    if source_type == DiscoverySourceType.COMPANY:
        return DiscoverySource(
            source_type,
            value,
            name=value,
            url="https://www.linkedin.com/company/example/",
        )
    return DiscoverySource(source_type, value)


class DiscoveryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.observed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def diagnostics(self):
        return CollectionRunDiagnostics.start("discover", self.observed_at)

    def test_dispatches_all_four_source_types_sequentially(self):
        sources = [
            source(DiscoverySourceType.KEYWORD, "SaaS"),
            source(DiscoverySourceType.HASHTAG, "saas"),
            source(DiscoverySourceType.CREATOR, "Creator"),
            source(DiscoverySourceType.COMPANY, "Company"),
        ]
        adapters = {item.source_type: FakeAdapter() for item in sources}
        context = FakeContext()
        diagnostics = self.diagnostics()

        discover_posts(
            context, FakeDB(), FakeParser(), self.observed_at, diagnostics,
            sources=sources, adapters=adapters,
        )

        self.assertEqual(len(context.pages), 4)
        self.assertTrue(all(page.closed for page in context.pages))
        for item in sources:
            self.assertEqual(adapters[item.source_type].calls[0][1], item)
        self.assertEqual(
            [item.status for item in diagnostics.source_diagnostics],
            ["empty", "empty", "empty", "empty"],
        )

    def test_default_registry_supports_all_source_types(self):
        self.assertEqual(
            set(build_source_adapters()),
            set(DiscoverySourceType),
        )

    def test_shared_candidate_pipeline_persists_complete_source(self):
        item = source(DiscoverySourceType.HASHTAG, "aiagents")
        adapter = FakeAdapter(candidate_count=1)
        parser = FakeParser(
            canonical_url="https://www.linkedin.com/posts/example-activity-123-abcd/"
        )
        database = FakeDB()
        diagnostics = self.diagnostics()

        discover_posts(
            FakeContext(), database, parser, self.observed_at, diagnostics,
            sources=[item], adapters={item.source_type: adapter},
        )

        self.assertEqual(parser.parsed_sources, ["aiagents"])
        self.assertIs(database.observations[0][2], item)
        saved_post = database.observations[0][0]
        self.assertEqual(saved_post.activity_id, "123")
        self.assertEqual(
            saved_post.post_url,
            "https://www.linkedin.com/posts/example-activity-123-abcd/",
        )
        source_run = diagnostics.source_diagnostics[0]
        self.assertEqual(source_run.valid_posts, 1)
        self.assertEqual(source_run.posts_saved, 1)
        self.assertEqual(source_run.canonical_urls_resolved, 1)
        self.assertEqual(source_run.directly_refreshable_posts, 1)
        self.assertEqual(diagnostics.discovery.posts_saved, 1)

    def test_candidate_limit_is_per_source_and_reported(self):
        item = source(DiscoverySourceType.KEYWORD, "SaaS")
        parser = FakeParser()
        diagnostics = self.diagnostics()

        discover_posts(
            FakeContext(), FakeDB(), parser, self.observed_at, diagnostics,
            max_candidates_per_source=2,
            sources=[item],
            adapters={item.source_type: FakeAdapter(candidate_count=5)},
        )

        source_run = diagnostics.source_diagnostics[0]
        self.assertEqual(len(parser.parsed_sources), 2)
        self.assertEqual(source_run.candidates_found, 5)
        self.assertEqual(source_run.candidates_truncated, 3)
        self.assertEqual(source_run.skips_by_reason["candidate_limit"], 3)
        self.assertEqual(
            diagnostics.discovery.skips_by_reason["candidate_limit"], 3
        )

    def test_source_failure_is_recorded_and_later_source_continues(self):
        failed = source(DiscoverySourceType.CREATOR, "Broken Creator")
        later = source(DiscoverySourceType.COMPANY, "Working Company")
        context = FakeContext()
        diagnostics = self.diagnostics()

        discover_posts(
            context,
            FakeDB(),
            FakeParser(),
            self.observed_at,
            diagnostics,
            sources=[failed, later],
            adapters={
                failed.source_type: FakeAdapter(
                    error=RuntimeError("checkpoint redirect " + "x" * 500)
                ),
                later.source_type: FakeAdapter(candidate_count=0),
            },
        )

        self.assertEqual(
            [item.status for item in diagnostics.source_diagnostics],
            ["failed", "empty"],
        )
        error = diagnostics.source_diagnostics[0].errors[0]
        self.assertEqual(error["source_type"], "creator")
        self.assertEqual(error["source_value"], "Broken Creator")
        self.assertEqual(error["stage"], "load_candidates")
        self.assertEqual(error["error_type"], "RuntimeError")
        self.assertLessEqual(len(error["message"]), 300)
        self.assertTrue(all(page.closed for page in context.pages))

    def test_authentication_failure_stops_discovery_before_later_sources(self):
        failed = source(DiscoverySourceType.KEYWORD, "SaaS")
        later = source(DiscoverySourceType.HASHTAG, "saas")
        later_adapter = FakeAdapter()
        context = FakeContext()
        diagnostics = self.diagnostics()

        with self.assertRaises(LinkedInAuthenticationError):
            discover_posts(
                context,
                FakeDB(),
                FakeParser(),
                self.observed_at,
                diagnostics,
                sources=[failed, later],
                adapters={
                    failed.source_type: FakeAdapter(
                        error=LinkedInAuthenticationError("session expired")
                    ),
                    later.source_type: later_adapter,
                },
            )

        self.assertEqual(len(context.pages), 1)
        self.assertEqual(later_adapter.calls, [])
        self.assertEqual(diagnostics.source_diagnostics[0].status, "failed")
        self.assertEqual(
            diagnostics.source_diagnostics[0].errors[0]["stage"],
            "authentication",
        )

    def test_authentication_failure_stops_refresh_after_first_target(self):
        diagnostics = CollectionRunDiagnostics.start("refresh", self.observed_at)

        with patch(
            "main.LinkedInTracker.refresh",
            side_effect=LinkedInAuthenticationError("session expired"),
        ) as refresh:
            with self.assertRaises(LinkedInAuthenticationError):
                refresh_posts(
                    FakeContext(), FakeDB(), FakeParser(), self.observed_at,
                    max_track_days=5, refresh_limit=15, diagnostics=diagnostics,
                )

        self.assertEqual(refresh.call_count, 1)
        self.assertEqual(diagnostics.refresh.attempts, 1)
        self.assertEqual(diagnostics.refresh.failures, 0)
        self.assertEqual(diagnostics.errors[0]["stage"], "authentication")

    def test_dashboard_supports_new_multi_source_and_legacy_posts(self):
        new_post = {
            "keyword": "SaaS",
            "discovery_sources": [
                {"type": "keyword", "value": "SaaS"},
                {"type": "hashtag", "value": "saas"},
            ],
        }
        legacy_post = {"keyword": "AI Agents"}

        self.assertEqual(
            normalized_discovery_sources(new_post),
            [
                {"type": "keyword", "value": "SaaS"},
                {"type": "hashtag", "value": "saas"},
            ],
        )
        self.assertEqual(
            normalized_discovery_sources(legacy_post),
            [{"type": "keyword", "value": "AI Agents"}],
        )

        post = {
            "post_id": "one",
            "first_seen_at": self.observed_at,
            **new_post,
        }
        snapshots = [
            {"post_id": "one", "observed_at": self.observed_at,
             "likes": 1, "comments": 0, "reposts": 0},
            {"post_id": "one", "observed_at": self.observed_at.replace(hour=2),
             "likes": 4, "comments": 0, "reposts": 0},
        ]
        trend = build_trend_rows([post], snapshots)[0]
        self.assertEqual(trend["source_types"], ["hashtag", "keyword"])
        self.assertEqual(trend["source_values"], ["SaaS", "saas"])

    def test_dashboard_filters_sources_and_flattens_source_health(self):
        rows = [{
            "source_types": ["keyword", "hashtag"],
            "source_values": ["SaaS", "saas"],
            "weighted_growth": 5,
            "post_age_hours": 2,
        }]
        self.assertEqual(
            filter_trend_rows(
                rows, source_types=["hashtag"], source_values=["saas"]
            ),
            rows,
        )
        self.assertEqual(
            filter_trend_rows(rows, source_values=["missing"]),
            [],
        )

        diagnostics = self.diagnostics()
        item = source(DiscoverySourceType.KEYWORD, "SaaS")
        per_source = diagnostics.begin_source(item)
        per_source.candidates_found = 2
        per_source.posts_saved = 1
        per_source.finalize()
        health = build_source_health_rows([diagnostics.to_document()])
        self.assertEqual(health[0]["source_type"], "keyword")
        self.assertEqual(health[0]["posts_saved"], 1)

    def test_candidate_limit_cli_option_is_positive(self):
        with patch("sys.argv", ["main.py", "--max-candidates-per-source", "12"]):
            self.assertEqual(parse_args().max_candidates_per_source, 12)
        with patch("sys.argv", ["main.py", "--max-candidates-per-source", "0"]):
            with self.assertRaises(SystemExit):
                parse_args()

    def test_cli_defaults_use_conservative_collection_limits(self):
        with patch("sys.argv", ["main.py"]):
            args = parse_args()

        self.assertEqual(args.refresh_limit, 15)
        self.assertEqual(args.max_candidates_per_source, 5)
        self.assertEqual(args.max_post_age_days, 5)


if __name__ == "__main__":
    unittest.main()

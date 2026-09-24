import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from database.mongo import MongoDB
from main import collect_once
from models.collection_run import CollectionRunDiagnostics, MAX_RUN_ERRORS


class FakeCollection:
    def __init__(self):
        self.documents = []

    def insert_one(self, document):
        self.documents.append(dict(document))

    def update_one(self, query, update):
        document = next(item for item in self.documents if item["run_id"] == query["run_id"])
        document.update(update["$set"])


class FakeDiagnosticsDB:
    def __init__(self):
        self.started = []
        self.finished = []

    def start_collection_run(self, diagnostics):
        self.started.append(diagnostics.to_document())

    def finish_collection_run(self, diagnostics):
        self.finished.append(diagnostics.to_document())


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.started_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def test_successful_run_is_persisted_as_completed(self):
        diagnostics = CollectionRunDiagnostics.start("discover", self.started_at)
        collection = FakeCollection()
        db = MongoDB.__new__(MongoDB)
        db.collection_runs = collection

        db.start_collection_run(diagnostics)
        diagnostics.discovery.candidates_found = 4
        diagnostics.discovery.valid_posts_found = 3
        diagnostics.discovery.posts_saved = 2
        diagnostics.finalize(finished_at=self.started_at + timedelta(seconds=2))
        db.finish_collection_run(diagnostics)

        document = collection.documents[0]
        self.assertEqual(document["status"], "completed")
        self.assertEqual(document["duration_seconds"], 2.0)
        self.assertEqual(document["discovery"]["posts_saved"], 2)
        self.assertEqual(document["refresh"]["attempts"], 0)

    def test_item_failure_finalizes_run_as_partial(self):
        diagnostics = CollectionRunDiagnostics.start("refresh", self.started_at)
        diagnostics.refresh.attempts += 2
        diagnostics.refresh.successes += 1
        diagnostics.refresh.record_failure("not_found")
        diagnostics.finalize(finished_at=self.started_at + timedelta(seconds=1))

        document = diagnostics.to_document()
        self.assertEqual(document["status"], "partial")
        self.assertEqual(document["refresh"]["failures"], 1)
        self.assertEqual(document["refresh"]["failures_by_status"], {"not_found": 1})

    def test_top_level_failure_finalizes_run_as_failed(self):
        diagnostics = CollectionRunDiagnostics.start("all", self.started_at)
        diagnostics.add_error("collection", RuntimeError("browser stopped"))
        diagnostics.finalize(
            failed=True,
            finished_at=self.started_at + timedelta(milliseconds=250),
        )

        self.assertEqual(diagnostics.status, "failed")
        self.assertEqual(diagnostics.duration_seconds, 0.25)
        self.assertEqual(diagnostics.errors[0]["error_type"], "RuntimeError")

    def test_counter_aggregation_and_errors_are_bounded(self):
        diagnostics = CollectionRunDiagnostics.start("all", self.started_at)
        for reason in ("not_post", "not_post", "no_identity"):
            diagnostics.discovery.increment_skip(reason)
        for reason in ("missing_author", "missing_author", "missing_reactions"):
            diagnostics.discovery.increment_quality_warning(reason)
        for index in range(MAX_RUN_ERRORS + 5):
            diagnostics.add_error("discovery", f"error {index} " + "x" * 500)

        self.assertEqual(
            diagnostics.discovery.skips_by_reason,
            {"not_post": 2, "no_identity": 1},
        )
        self.assertEqual(
            diagnostics.discovery.quality_warnings_by_reason,
            {"missing_author": 2, "missing_reactions": 1},
        )
        self.assertEqual(len(diagnostics.errors), MAX_RUN_ERRORS)
        self.assertEqual(diagnostics.error_count, MAX_RUN_ERRORS + 5)
        self.assertLessEqual(len(diagnostics.errors[-1]["message"]), 300)

    def test_collection_exception_still_finalizes_persisted_run(self):
        db = FakeDiagnosticsDB()
        args = SimpleNamespace(
            mode="discover",
            headless=True,
            max_post_age_days=7,
            refresh_limit=100,
            min_window_hours=1,
            min_growth=3,
        )

        with patch("main.sync_playwright", side_effect=RuntimeError("browser unavailable")):
            with self.assertRaisesRegex(RuntimeError, "browser unavailable"):
                collect_once(db, args)

        self.assertEqual(len(db.started), 1)
        self.assertEqual(db.started[0]["status"], "running")
        self.assertEqual(len(db.finished), 1)
        self.assertEqual(db.finished[0]["status"], "failed")
        self.assertIsNotNone(db.finished[0]["finished_at"])


if __name__ == "__main__":
    unittest.main()

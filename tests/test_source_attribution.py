import copy
import unittest
from datetime import datetime, timedelta, timezone

from config.discovery_source import DiscoverySource, DiscoverySourceType
from database.mongo import MongoDB
from models.post import Post


class FakeCollection:
    def __init__(self):
        self.documents = []

    def update_one(self, query, update, upsert=False):
        document = next(
            (item for item in self.documents if self._matches(item, query)),
            None,
        )
        inserted = document is None
        if inserted:
            if not upsert:
                return
            document = copy.deepcopy(query)
            self.documents.append(document)

        if inserted:
            document.update(copy.deepcopy(update.get("$setOnInsert", {})))
        document.update(copy.deepcopy(update.get("$set", {})))
        for field, value in update.get("$addToSet", {}).items():
            values = document.setdefault(field, [])
            if value not in values:
                values.append(copy.deepcopy(value))

    def find(self, query=None, projection=None):
        query = query or {}
        return [
            copy.deepcopy(item)
            for item in self.documents
            if self._matches(item, query)
        ]

    def find_one(self, query):
        document = next(
            (item for item in self.documents if self._matches(item, query)),
            None,
        )
        return copy.deepcopy(document)

    def delete_many(self, query):
        self.documents = [
            item for item in self.documents if not self._matches(item, query)
        ]

    def delete_one(self, query):
        for index, item in enumerate(self.documents):
            if self._matches(item, query):
                del self.documents[index]
                return

    @staticmethod
    def _matches(document, query):
        for key, expected in query.items():
            actual = document.get(key)
            if not isinstance(expected, dict):
                if actual != expected:
                    return False
                continue
            if expected.get("$type") == "string" and not isinstance(actual, str):
                return False
            if "$ne" in expected and actual == expected["$ne"]:
                return False
        return True


class SourceAttributionTests(unittest.TestCase):
    def setUp(self):
        self.observed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.db = MongoDB.__new__(MongoDB)
        self.db.collection = FakeCollection()
        self.db.snapshots = FakeCollection()

    def save(self, source=None, observed_at=None):
        post = Post(
            keyword="legacy keyword",
            author="Ada",
            text="A stable post body",
            likes=10,
            comments=2,
            reposts=1,
        )
        saved = self.db.save_observation(
            post,
            observed_at or self.observed_at,
            source,
        )
        self.assertTrue(saved)
        return self.db.collection.documents[0]

    def test_all_source_types_are_stored_as_normalized_documents(self):
        cases = (
            (
                DiscoverySource(DiscoverySourceType.KEYWORD, "AI Agents"),
                {"type": "keyword", "value": "AI Agents"},
            ),
            (
                DiscoverySource(DiscoverySourceType.HASHTAG, "AgenticAI"),
                {"type": "hashtag", "value": "AgenticAI"},
            ),
            (
                DiscoverySource(
                    DiscoverySourceType.CREATOR,
                    "Jane Doe",
                    name="Jane Doe",
                    url="https://www.linkedin.com/in/jane-doe/",
                ),
                {
                    "type": "creator",
                    "value": "Jane Doe",
                    "name": "Jane Doe",
                    "url": "https://www.linkedin.com/in/jane-doe/",
                },
            ),
            (
                DiscoverySource(
                    DiscoverySourceType.COMPANY,
                    "Example Inc",
                    name="Example Inc",
                    url="https://www.linkedin.com/company/example-inc/",
                ),
                {
                    "type": "company",
                    "value": "Example Inc",
                    "name": "Example Inc",
                    "url": "https://www.linkedin.com/company/example-inc/",
                },
            ),
        )

        for source, expected in cases:
            with self.subTest(source_type=source.source_type):
                self.setUp()
                document = self.save(source)
                self.assertEqual(document["discovery_sources"], [expected])

    def test_repeated_discovery_does_not_duplicate_a_source(self):
        source = DiscoverySource(DiscoverySourceType.HASHTAG, "AgenticAI")

        self.save(source)
        document = self.save(source, self.observed_at + timedelta(hours=1))

        self.assertEqual(
            document["discovery_sources"],
            [{"type": "hashtag", "value": "AgenticAI"}],
        )

    def test_one_post_retains_multiple_source_origins(self):
        sources = (
            DiscoverySource(DiscoverySourceType.KEYWORD, "AI Agents"),
            DiscoverySource(DiscoverySourceType.HASHTAG, "AgenticAI"),
            DiscoverySource(
                DiscoverySourceType.COMPANY,
                "Example Inc",
                name="Example Inc",
                url="https://www.linkedin.com/company/example-inc/",
            ),
        )

        for offset, source in enumerate(sources):
            document = self.save(
                source,
                self.observed_at + timedelta(hours=offset),
            )

        self.assertEqual(
            document["discovery_sources"],
            [
                {"type": "keyword", "value": "AI Agents"},
                {"type": "hashtag", "value": "AgenticAI"},
                {
                    "type": "company",
                    "value": "Example Inc",
                    "name": "Example Inc",
                    "url": "https://www.linkedin.com/company/example-inc/",
                },
            ],
        )

    def test_legacy_call_preserves_keyword_and_adds_keyword_attribution(self):
        document = self.save()

        self.assertEqual(document["keyword"], "legacy keyword")
        self.assertEqual(
            document["discovery_sources"],
            [{"type": "keyword", "value": "legacy keyword"}],
        )

    def test_identity_promotion_preserves_previous_source_origins(self):
        keyword = DiscoverySource(DiscoverySourceType.KEYWORD, "AI Agents")
        hashtag = DiscoverySource(DiscoverySourceType.HASHTAG, "AgenticAI")
        self.save(keyword)

        promoted = Post(
            keyword="legacy keyword",
            activity_id="123456",
            author="Ada",
            text="A stable post body",
            likes=12,
            comments=3,
            reposts=1,
        )
        self.assertTrue(self.db.save_observation(
            promoted,
            self.observed_at + timedelta(hours=1),
            hashtag,
        ))

        self.assertEqual(len(self.db.collection.documents), 1)
        document = self.db.collection.documents[0]
        self.assertEqual(document["post_id"], "123456")
        self.assertEqual(document["discovery_sources"], [
            {"type": "keyword", "value": "AI Agents"},
            {"type": "hashtag", "value": "AgenticAI"},
        ])

    def test_non_keyword_source_does_not_overwrite_legacy_keyword(self):
        self.save(DiscoverySource(DiscoverySourceType.KEYWORD, "AI Agents"))
        document = self.save(
            DiscoverySource(DiscoverySourceType.HASHTAG, "aiagents"),
            self.observed_at + timedelta(hours=1),
        )

        self.assertEqual(document["keyword"], "legacy keyword")


if __name__ == "__main__":
    unittest.main()

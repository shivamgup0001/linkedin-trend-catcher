from pymongo import ASCENDING, MongoClient
from dotenv import load_dotenv
from dataclasses import asdict
import hashlib
import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

from config.discovery_source import DiscoverySource, DiscoverySourceType

load_dotenv()

class MongoDB:

    def __init__(self):
        self.client = MongoClient(os.getenv("MONGO_URI"), serverSelectionTimeoutMS=5000)
        self.db = self.client[os.getenv("DB_NAME")]
        self.collection = self.db[os.getenv("COLLECTION_NAME")]
        self.snapshots = self.db["post_snapshots"]
        self.collection_runs = self.db["collection_runs"]
        self.collection.create_index(
            "post_id", unique=True,
            partialFilterExpression={"post_id": {"$type": "string"}},
        )
        self.snapshots.create_index(
            [("post_id", ASCENDING), ("observed_at", ASCENDING)], unique=True
        )
        self.snapshots.create_index("observed_at")
        self.collection_runs.create_index("run_id", unique=True)
        self.collection_runs.create_index("started_at")
        self.collection_runs.create_index("status")

    def start_collection_run(self, diagnostics):
        self.collection_runs.insert_one(diagnostics.to_document())

    def finish_collection_run(self, diagnostics):
        self.collection_runs.update_one(
            {"run_id": diagnostics.run_id},
            {"$set": diagnostics.to_document()},
        )

    def save_observation(
        self,
        post,
        observed_at,
        discovery_source: Optional[DiscoverySource] = None,
    ):
        post_id, identity_source = self._get_post_id(post)
        if not post_id:
            return False

        if post.activity_id and not post.post_url:
            post.post_url = f"https://www.linkedin.com/feed/update/urn:li:activity:{post.activity_id}/"

        if identity_source != "content_fingerprint":
            self._promote_previous_identities(post, post_id)

        details = asdict(post)
        for field in ("likes", "comments", "reposts", "scraped_at"):
            details.pop(field)
        if (
            discovery_source is not None
            and discovery_source.source_type != DiscoverySourceType.KEYWORD
        ):
            # The legacy field represents keyword discovery only. Non-keyword
            # observations must not overwrite a keyword captured previously.
            details.pop("keyword", None)
        details["post_id"] = post_id
        details["identity_source"] = identity_source
        details["last_seen_at"] = observed_at
        update = {
            "$set": details,
            "$setOnInsert": {"first_seen_at": observed_at},
        }
        source_document = self._discovery_source_document(post, discovery_source)
        if source_document is not None:
            update["$addToSet"] = {"discovery_sources": source_document}
        self.collection.update_one(
            {"post_id": post_id},
            update,
            upsert=True,
        )
        self.snapshots.update_one(
            {"post_id": post_id, "observed_at": observed_at},
            {"$setOnInsert": {
                "likes": post.likes,
                "comments": post.comments,
                "reposts": post.reposts,
                "source": "discovery",
            }},
            upsert=True,
        )
        return True

    @staticmethod
    def _discovery_source_document(post, discovery_source):
        source = discovery_source
        if source is None and post.keyword:
            source = DiscoverySource(DiscoverySourceType.KEYWORD, post.keyword)
        if source is None:
            return None

        document = {
            "type": source.source_type.value,
            "value": source.value,
        }
        if source.source_type in {
            DiscoverySourceType.CREATOR,
            DiscoverySourceType.COMPANY,
        }:
            document["name"] = source.name or source.value
            document["url"] = source.url
        return document

    def save_snapshot(self, post_id, observed_at, likes, comments, reposts, source):
        self.snapshots.update_one(
            {"post_id": post_id, "observed_at": observed_at},
            {"$set": {
                "likes": likes,
                "comments": comments,
                "reposts": reposts,
                "source": source,
            }},
            upsert=True,
        )
        update = {"last_checked_at": observed_at}
        if source == "direct_refresh":
            update.update({
                "last_refresh_status": "ok",
                "last_refresh_error": None,
                "refresh_failure_count": 0,
            })
        self.collection.update_one({"post_id": post_id}, {"$set": update})

    def save_refresh_failure(self, post_id, observed_at, status, detail=None):
        self.collection.update_one(
            {"post_id": post_id},
            {
                "$set": {
                    "last_checked_at": observed_at,
                    "last_refresh_status": status,
                    "last_refresh_error": detail,
                },
                "$inc": {"refresh_failure_count": 1},
            },
        )

    def refresh_targets(self, max_track_days, limit=100):
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_track_days)
        return self.collection.find({
            "post_url": {"$regex": r"linkedin\.com/(?:feed/update/|posts/)"},
            "first_seen_at": {"$gte": cutoff},
            "tracking_enabled": {"$ne": False},
        }).sort("last_checked_at", ASCENDING).limit(limit)

    @staticmethod
    def _get_post_id(post):
        if post.activity_id:
            return post.activity_id, "linkedin_activity"
        if post.post_url:
            return post.post_url, "linkedin_url"
        fingerprint = MongoDB._content_fingerprint(post)
        return (fingerprint, "content_fingerprint") if fingerprint else (None, None)

    @staticmethod
    def _content_fingerprint(post):
        if not post.text:
            return None

        author = post.author_url or post.author or "unknown-author"
        if post.author_url:
            parts = urlsplit(post.author_url)
            author = urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))
        normalized_author = unicodedata.normalize("NFKC", author).strip().lower()
        normalized_text = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", post.text)).strip()
        if not normalized_text:
            return None

        digest = hashlib.sha256(f"{normalized_author}\0{normalized_text}".encode("utf-8")).hexdigest()
        return f"fingerprint:{digest}"

    def _promote_previous_identities(self, post, stable_post_id):
        fingerprint = self._content_fingerprint(post)
        aliases = set()
        if fingerprint and fingerprint != stable_post_id:
            aliases.add(fingerprint)
        if post.text:
            identity_match = {"text": post.text, "post_id": {"$type": "string", "$ne": stable_post_id}}
            if post.author_url:
                identity_match["author_url"] = post.author_url
            elif post.author:
                identity_match["author"] = post.author
            aliases.update(document["post_id"] for document in self.collection.find(identity_match, {"post_id": 1}))

        for alias in aliases:
            self._merge_identity(alias, stable_post_id)

    def _merge_identity(self, old_post_id, stable_post_id):
        old_post = self.collection.find_one({"post_id": old_post_id})
        if old_post is None:
            return
        for snapshot in self.snapshots.find({"post_id": old_post_id}):
            observed_at = snapshot.pop("observed_at")
            snapshot.pop("_id", None)
            snapshot.pop("post_id", None)
            self.snapshots.update_one(
                {"post_id": stable_post_id, "observed_at": observed_at},
                {"$set": snapshot},
                upsert=True,
            )
        for source in old_post.get("discovery_sources", []):
            self.collection.update_one(
                {"post_id": stable_post_id},
                {"$addToSet": {"discovery_sources": source}},
                upsert=True,
            )
        self.snapshots.delete_many({"post_id": old_post_id})
        self.collection.delete_one({"post_id": old_post_id})

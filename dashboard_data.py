"""Read-only data access and transformations for the Streamlit dashboard."""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import os
import re

from dotenv import load_dotenv
from pymongo import MongoClient

from analytics.growth import growth_between, trend_scores


NOT_ATTEMPTED = "not attempted"
SUPPORTED_LINKEDIN_URL = re.compile(
    r"^https://(?:www\.)?linkedin\.com/(?:feed/update/|posts/)", re.IGNORECASE
)
RELATIVE_AGE = re.compile(r"^(\d+)(mo|s|m|h|d|w|y)$")
AGE_IN_HOURS = {
    "s": 1 / 3600,
    "m": 1 / 60,
    "h": 1,
    "d": 24,
    "w": 168,
    "mo": 720,
    "y": 8760,
}


class DashboardConfigurationError(RuntimeError):
    """Raised when the dashboard cannot identify its MongoDB collections."""


def _as_utc(value):
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def latest_snapshot(snapshots):
    """Return the newest timestamped snapshot, regardless of input order."""
    valid = [item for item in snapshots if _as_utc(item.get("observed_at")) is not None]
    if not valid:
        return None
    return max(valid, key=lambda item: _as_utc(item["observed_at"]))


def eligible_baseline(snapshots, current, min_window_hours):
    current_time = _as_utc(current.get("observed_at"))
    if current_time is None:
        return None
    cutoff = current_time - timedelta(hours=min_window_hours)
    eligible = [
        item
        for item in snapshots
        if item is not current
        and _as_utc(item.get("observed_at")) is not None
        and _as_utc(item["observed_at"]) <= cutoff
    ]
    if not eligible:
        return None
    return max(eligible, key=lambda item: _as_utc(item["observed_at"]))


def post_age_hours(post, observed_at):
    """Estimate age using LinkedIn's stored relative age and collection time."""
    observed = _as_utc(observed_at)
    if observed is None:
        return None

    match = RELATIVE_AGE.fullmatch(str(post.get("posted_at") or "").strip())
    reference = _as_utc(post.get("last_seen_at"))
    if match:
        relative_age = int(match.group(1)) * AGE_IN_HOURS[match.group(2)]
        elapsed = max(0, (observed - reference).total_seconds() / 3600) if reference else 0
        return round(relative_age + elapsed, 2)

    first_seen = _as_utc(post.get("first_seen_at"))
    if first_seen:
        return round(max(0, (observed - first_seen).total_seconds() / 3600), 2)
    return None


def refresh_status(post):
    return post.get("last_refresh_status") or NOT_ATTEMPTED


def is_directly_refreshable(post):
    return (
        post.get("tracking_enabled") is not False
        and bool(SUPPORTED_LINKEDIN_URL.match(str(post.get("post_url") or "")))
    )


def normalized_discovery_sources(post):
    """Return deduplicated attribution, including legacy keyword-only posts."""
    sources = []
    seen = set()
    for source in post.get("discovery_sources") or []:
        source_type = source.get("type")
        value = source.get("value")
        if not source_type or not value:
            continue
        normalized = {"type": source_type, "value": value}
        if source.get("name") is not None:
            normalized["name"] = source["name"]
        if source.get("url") is not None:
            normalized["url"] = source["url"]
        key = (source_type.casefold(), str(source.get("url") or value).casefold())
        if key not in seen:
            seen.add(key)
            sources.append(normalized)

    keyword = post.get("keyword")
    legacy_key = ("keyword", str(keyword).casefold()) if keyword else None
    if legacy_key and legacy_key not in seen:
        sources.append({"type": "keyword", "value": keyword})
    return sources


def build_post_selector_options(posts, preview_length=80):
    """Build newest-first labels for selecting any saved post."""
    options = []
    minimum = datetime.min.replace(tzinfo=timezone.utc)
    for post in posts:
        post_id = post.get("post_id")
        if not post_id:
            continue
        author = post.get("author") or "Unknown author"
        text = " ".join(str(post.get("text") or "").split())
        if len(text) > preview_length:
            text = text[: preview_length - 3].rstrip() + "..."
        label = f"{author} | {text}" if text else f"{author} | {post_id}"
        options.append({
            "post_id": post_id,
            "label": label,
            "last_seen_at": _as_utc(post.get("last_seen_at")) or minimum,
        })
    options.sort(
        key=lambda item: (item["last_seen_at"], str(item["post_id"])),
        reverse=True,
    )
    return options


def build_trend_rows(posts, snapshots, min_window_hours=1):
    """Build ranked rows from each post's latest eligible snapshot pair."""
    snapshots_by_post = defaultdict(list)
    for snapshot in snapshots:
        post_id = snapshot.get("post_id")
        if post_id:
            snapshots_by_post[post_id].append(snapshot)

    rows = []
    for post in posts:
        post_id = post.get("post_id")
        history = snapshots_by_post.get(post_id, [])
        current = latest_snapshot(history)
        if current is None:
            continue
        baseline = eligible_baseline(history, current, min_window_hours)
        if baseline is None:
            continue
        normalized_baseline = {
            **baseline,
            "observed_at": _as_utc(baseline.get("observed_at")),
        }
        normalized_current = {
            **current,
            "observed_at": _as_utc(current.get("observed_at")),
        }
        growth = growth_between(normalized_baseline, normalized_current)
        if growth is None:
            continue

        valid_snapshot_count = sum(
            _as_utc(item.get("observed_at")) is not None for item in history
        )
        scores = trend_scores(growth, valid_snapshot_count)

        changes = growth["changes"]
        metrics = growth["current_metrics"]
        attributed_sources = normalized_discovery_sources(post)
        rows.append({
            "post_id": post_id,
            "author": post.get("author") or "Unknown",
            "keyword": post.get("keyword") or "Unknown",
            "post_age_hours": post_age_hours(post, current.get("observed_at")),
            "reactions": metrics.get("likes"),
            "comments": metrics.get("comments"),
            "reposts": metrics.get("reposts"),
            "reaction_growth": changes.get("likes"),
            "comment_growth": changes.get("comments"),
            "repost_growth": changes.get("reposts"),
            "weighted_growth": growth["weighted_growth"],
            "score_per_hour": growth["score_per_hour"],
            **scores,
            "observation_hours": growth["hours"],
            "last_observation": growth["current_observed_at"],
            "baseline_observation": growth["previous_observed_at"],
            "refresh_status": refresh_status(post),
            "post_url": post.get("post_url"),
            "discovery_sources": attributed_sources,
            "source_types": sorted({
                source["type"] for source in attributed_sources
            }),
            "source_values": sorted({
                source["value"] for source in attributed_sources
            }),
        })

    return rank_trend_rows(rows, "momentum")


def rank_trend_rows(rows, ranking="momentum"):
    """Sort trend rows using one of the dashboard's supported ranking views."""
    score_field = {
        "momentum": "momentum_score",
        "breakout": "breakout_score",
    }.get(ranking)
    if score_field is None:
        raise ValueError(f"Unsupported trend ranking: {ranking}")
    return sorted(rows, key=lambda item: (
        -(item.get(score_field) or 0),
        -(item.get("weighted_growth") or 0),
        str(item.get("post_id")),
    ))


def filter_trend_rows(
    rows,
    keywords=None,
    authors=None,
    min_growth=0,
    max_post_age_days=None,
    statuses=None,
    source_types=None,
    source_values=None,
):
    keyword_set = set(keywords or [])
    author_set = set(authors or [])
    status_set = set(statuses or [])
    source_type_set = set(source_types or [])
    source_value_set = set(source_values or [])
    maximum_hours = max_post_age_days * 24 if max_post_age_days is not None else None

    filtered = []
    for row in rows:
        if keyword_set and row.get("keyword") not in keyword_set:
            continue
        if author_set and row.get("author") not in author_set:
            continue
        if status_set and row.get("refresh_status") not in status_set:
            continue
        if source_type_set and not source_type_set.intersection(
            row.get("source_types") or []
        ):
            continue
        if source_value_set and not source_value_set.intersection(
            row.get("source_values") or []
        ):
            continue
        if (row.get("weighted_growth") or 0) < min_growth:
            continue
        age = row.get("post_age_hours")
        if maximum_hours is not None and (age is None or age > maximum_hours):
            continue
        filtered.append(row)
    return filtered


def build_overview(posts, snapshots):
    posts = list(posts)
    snapshots = list(snapshots)
    snapshot_counts = defaultdict(int)
    observed_times = []
    for snapshot in snapshots:
        post_id = snapshot.get("post_id")
        if post_id:
            snapshot_counts[post_id] += 1
        observed = _as_utc(snapshot.get("observed_at"))
        if observed is not None:
            observed_times.append(observed)

    return {
        "total_posts": len(posts),
        "directly_refreshable": sum(is_directly_refreshable(post) for post in posts),
        "posts_with_two_snapshots": sum(count >= 2 for count in snapshot_counts.values()),
        "failed_refreshes": sum(
            post.get("last_refresh_status") not in (None, "ok") for post in posts
        ),
        "latest_snapshot_time": max(observed_times) if observed_times else None,
        "keywords": sorted({post["keyword"] for post in posts if post.get("keyword")}),
    }


def build_collection_run_rows(runs):
    """Flatten persisted run diagnostics for display, newest first."""
    rows = []
    for run in runs:
        discovery = run.get("discovery") or {}
        refresh = run.get("refresh") or {}
        sources = run.get("active_discovery_sources") or []
        rows.append({
            "run_id": run.get("run_id"),
            "mode": run.get("mode") or "unknown",
            "status": run.get("status") or "unknown",
            "started_at": _as_utc(run.get("started_at")),
            "finished_at": _as_utc(run.get("finished_at")),
            "duration_seconds": run.get("duration_seconds"),
            "active_sources": ", ".join(
                f"{source.get('type', 'unknown')}: {source.get('value', 'unknown')}"
                for source in sources
            ),
            "candidates_found": discovery.get("candidates_found", 0),
            "valid_posts_found": discovery.get("valid_posts_found", 0),
            "posts_saved": discovery.get("posts_saved", 0),
            "canonical_urls_resolved": discovery.get("canonical_urls_resolved", 0),
            "skips": sum((discovery.get("skips_by_reason") or {}).values()),
            "quality_warnings": sum(
                (discovery.get("quality_warnings_by_reason") or {}).values()
            ),
            "refresh_attempts": refresh.get("attempts", 0),
            "refresh_successes": refresh.get("successes", 0),
            "refresh_failures": refresh.get("failures", 0),
            "error_count": run.get("error_count", 0),
            "errors": run.get("errors") or [],
        })
    minimum = datetime.min.replace(tzinfo=timezone.utc)
    rows.sort(key=lambda item: item["started_at"] or minimum, reverse=True)
    return rows


def build_source_health_rows(runs):
    """Flatten new per-source diagnostics and tolerate legacy run documents."""
    rows = []
    minimum = datetime.min.replace(tzinfo=timezone.utc)
    for run in runs:
        started_at = _as_utc(run.get("started_at"))
        diagnostics = run.get("source_diagnostics")
        if diagnostics is None:
            diagnostics = [{
                "source_type": source.get("type"),
                "source_value": source.get("value"),
                "status": "unavailable",
            } for source in run.get("active_discovery_sources") or []]
        for source in diagnostics:
            rows.append({
                "run_id": run.get("run_id"),
                "started_at": started_at,
                "source_type": source.get("source_type") or "unknown",
                "source_value": source.get("source_value") or "unknown",
                "status": source.get("status") or "unknown",
                "candidates_found": source.get("candidates_found", 0),
                "candidates_truncated": source.get("candidates_truncated", 0),
                "valid_posts": source.get("valid_posts", 0),
                "posts_saved": source.get("posts_saved", 0),
                "canonical_urls_resolved": source.get(
                    "canonical_urls_resolved", 0
                ),
                "directly_refreshable_posts": source.get(
                    "directly_refreshable_posts", 0
                ),
                "skips": source.get("skips_by_reason") or {},
                "quality_warnings": (
                    source.get("quality_warnings_by_reason") or {}
                ),
                "errors": source.get("errors") or [],
            })
    rows.sort(key=lambda item: item["started_at"] or minimum, reverse=True)
    return rows


class DashboardDataAccess:
    """Small read-only boundary around the dashboard's MongoDB queries."""

    def __init__(
        self,
        post_collection,
        snapshot_collection,
        collection_run_collection=None,
        client=None,
    ):
        self.posts = post_collection
        self.snapshots = snapshot_collection
        self.collection_runs = collection_run_collection
        self.client = client

    @classmethod
    def from_env(cls):
        load_dotenv()
        missing = [
            name for name in ("MONGO_URI", "DB_NAME", "COLLECTION_NAME")
            if not os.getenv(name)
        ]
        if missing:
            raise DashboardConfigurationError(
                "Missing required MongoDB settings: " + ", ".join(missing)
            )
        client = MongoClient(os.getenv("MONGO_URI"), serverSelectionTimeoutMS=5000)
        database = client[os.getenv("DB_NAME")]
        return cls(
            database[os.getenv("COLLECTION_NAME")],
            database["post_snapshots"],
            database["collection_runs"],
            client,
        )

    def load_posts(self):
        return list(self.posts.find({}))

    def load_snapshots(self):
        return list(self.snapshots.find({}))

    def load_collection_runs(self, limit=50):
        if self.collection_runs is None:
            return []
        runs = list(self.collection_runs.find({}))
        minimum = datetime.min.replace(tzinfo=timezone.utc)
        runs.sort(
            key=lambda item: _as_utc(item.get("started_at")) or minimum,
            reverse=True,
        )
        return runs[:limit]

    def post_detail(self, post_id):
        post = self.posts.find_one({"post_id": post_id})
        history = list(self.snapshots.find({"post_id": post_id}))
        minimum = datetime.min.replace(tzinfo=timezone.utc)
        history.sort(key=lambda item: _as_utc(item.get("observed_at")) or minimum)
        return post, history

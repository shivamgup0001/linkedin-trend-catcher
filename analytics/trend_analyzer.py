from collections import Counter
from datetime import timedelta
import re
from analytics.growth import growth_between, trend_scores


AGE_IN_HOURS = {"s": 1 / 3600, "m": 1 / 60, "h": 1, "d": 24, "w": 168, "mo": 720, "y": 8760}

class TrendAnalyzer:

    def __init__(self, collection, snapshots=None):
        self.collection = collection
        self.snapshots = snapshots

    def top_trending(self, observed_at, limit=10, min_window_hours=1, min_growth=3, max_post_age_days=7):
        ranked = []
        baseline_cutoff = observed_at - timedelta(hours=min_window_hours)
        for current in self.snapshots.find({"observed_at": observed_at}):
            previous = self.snapshots.find_one(
                {
                    "post_id": current["post_id"],
                    "observed_at": {"$lte": baseline_cutoff},
                },
                sort=[("observed_at", -1)],
            )
            if previous is None:
                continue
            growth = growth_between(previous, current)
            if growth is None or growth["weighted_growth"] < min_growth:
                continue
            post = self.collection.find_one({"post_id": current["post_id"]}) or {}
            if not post:
                continue
            if self._post_age_hours(post, observed_at) > max_post_age_days * 24:
                continue
            snapshot_count = len(list(self.snapshots.find({"post_id": current["post_id"]})))
            ranked.append({
                "post_id": current["post_id"],
                "author": post.get("author"),
                "keyword": post.get("keyword"),
                "post_url": post.get("post_url"),
                "text": post.get("text"),
                "posted_at": post.get("posted_at"),
                **growth,
                **trend_scores(growth, snapshot_count),
            })
        ranked.sort(key=lambda item: (
            -item["momentum_score"],
            -item["weighted_growth"],
            str(item["post_id"]),
        ))
        return ranked[:limit]

    @staticmethod
    def _post_age_hours(post, observed_at):
        posted_at = post.get("posted_at") or ""
        match = re.fullmatch(r"(\d+)(mo|s|m|h|d|w|y)", posted_at)
        if match:
            return int(match.group(1)) * AGE_IN_HOURS[match.group(2)]
        first_seen = post.get("first_seen_at")
        if first_seen:
            if first_seen.tzinfo is None:
                first_seen = first_seen.replace(tzinfo=observed_at.tzinfo)
            return (observed_at - first_seen).total_seconds() / 3600
        return 0

    def generate_report(self):

        return {
            "summary": self.dataset_summary(),
            "top_authors": self.top_authors(),
            "top_hashtags": self.top_hashtags(),
            "top_engagement_posts": self.top_engagement_posts(),
            "keyword_distribution": self.keyword_distribution(),
            "average_metrics": self.average_metrics()
        }

    def top_authors(self, limit =10):

        authors = []

        for post in self.collection.find():

            if post.get("author"):
                authors.append(post["author"])

        counter = Counter(authors)

        return [
            {
                "author": author,
                "posts": count
            }
            for author, count in counter.most_common(limit)
        ]

    def top_hashtags(self, limit=10):

        hashtags = []

        for post in self.collection.find():

            text = post.get("text") or ""

            hashtags.extend(
                re.findall(r"#\w+", text)
            )

        counter = Counter(hashtags)

        return [
            {
                "hashtag": hashtag,
                "count": count
            }
            for hashtag, count in counter.most_common(limit)
        ]

    def top_engagement_posts(self, limit=10):

        posts = []

        for post in self.collection.find():
            snapshot = self._latest_snapshot(post.get("post_id"))
            if snapshot is None:
                continue
            likes = snapshot.get("likes") or 0
            comments = snapshot.get("comments") or 0
            reposts = snapshot.get("reposts") or 0

            score = likes + comments * 3 + reposts * 5

            posts.append({
                "author": post.get("author"),
                "keyword": post.get("keyword"),
                "likes": likes,
                "comments": comments,
                "reposts": reposts,
                "score": score,
                "post_url": post.get("post_url"),
                "observed_at": snapshot.get("observed_at"),
            })

        posts.sort(key=lambda p: p["score"], reverse=True)

        return posts[:limit]

    def keyword_distribution(self):

        keywords = []

        for post in self.collection.find():

            keyword = post.get("keyword")

            if keyword:
                keywords.append(keyword)

        counter = Counter(keywords)

        return [
            {
                "keyword": keyword,
                "posts": count
            }
            for keyword, count in counter.most_common()
        ]

    def average_metrics(self):

        total_likes = 0
        total_comments = 0
        total_reposts = 0
        total_posts = 0

        for post in self.collection.find():
            snapshot = self._latest_snapshot(post.get("post_id"))
            if snapshot is None:
                continue
            total_posts += 1
            total_likes += snapshot.get("likes") or 0
            total_comments += snapshot.get("comments") or 0
            total_reposts += snapshot.get("reposts") or 0

        if total_posts == 0:
            return {}

        return {
            "avg_likes": round(total_likes / total_posts, 2),
            "avg_comments": round(total_comments / total_posts, 2),
            "avg_reposts": round(total_reposts / total_posts, 2),
        }

    def _latest_snapshot(self, post_id):
        if self.snapshots is None or not post_id:
            return None
        return self.snapshots.find_one(
            {"post_id": post_id},
            sort=[("observed_at", -1)],
        )
    
    def dataset_summary(self):

        total_posts = self.collection.count_documents({})

        unique_authors = len(
            self.collection.distinct("author")
        )

        unique_keywords = len(
            self.collection.distinct("keyword")
        )

        return {
            "total_posts": total_posts,
            "unique_authors": unique_authors,
            "unique_keywords": unique_keywords
        }

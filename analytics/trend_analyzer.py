from collections import Counter
import re

class TrendAnalyzer:

    def __init__(self, collection):
        self.collection = collection

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

            likes = post.get("likes") or 0
            comments = post.get("comments") or 0
            reposts = post.get("reposts") or 0

            score = likes + comments * 3 + reposts * 5

            posts.append({
                "author": post.get("author"),
                "keyword": post.get("keyword"),
                "likes": likes,
                "comments": comments,
                "reposts": reposts,
                "score": score
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

            total_posts += 1

            total_likes += post.get("likes") or 0
            total_comments += post.get("comments") or 0
            total_reposts += post.get("reposts") or 0

        if total_posts == 0:
            return {}

        return {
            "avg_likes": round(total_likes / total_posts, 2),
            "avg_comments": round(total_comments / total_posts, 2),
            "avg_reposts": round(total_reposts / total_posts, 2),
        }
    
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
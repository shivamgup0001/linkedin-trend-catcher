class ReportPrinter:

    def print(self, report):

        print("\nDataset Summary")
        print("-" * 40)

        summary = report["summary"]

        print(f"Total Posts      : {summary['total_posts']}")
        print(f"Unique Authors   : {summary['unique_authors']}")
        print(f"Unique Keywords  : {summary['unique_keywords']}")

        print("\nTop Authors")
        print("-" * 40)

        for author in report["top_authors"]:
            print(f"{author['author']}: {author['posts']}")

        print("\nTop Hashtags")
        print("-" * 40)

        for hashtag in report["top_hashtags"]:
            print(f"{hashtag['hashtag']}: {hashtag['count']}")

        print("\nTop Engagement Posts")
        print("-" * 40)

        for post in report["top_engagement_posts"]:
            print(f"Author   : {post['author']}")
            print(f"Keyword  : {post['keyword']}")
            print(f"Score    : {post['score']}")
            print(f"Likes    : {post['likes']}")
            print(f"Comments : {post['comments']}")
            print(f"Reposts  : {post['reposts']}")
            print("-" * 40)

        print("\nKeyword Distribution")
        print("-" * 40)

        for keyword in report["keyword_distribution"]:
            print(f"{keyword['keyword']}: {keyword['posts']}")

        print("\nAverage Metrics")
        print("-" * 40)

        metrics = report["average_metrics"]

        print(f"Average Likes    : {metrics['avg_likes']}")
        print(f"Average Comments : {metrics['avg_comments']}")
        print(f"Average Reposts  : {metrics['avg_reposts']}")
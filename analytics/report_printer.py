class ReportPrinter:

    def print(slef, report):

        print("\nTop Authors")
        print("-" * 40)

        for author, count in report["top_authors"]:
            print(f"{author}: {count}")

        print("\nTop Hashtags")
        print("-" * 40)

        for hashtag, count in report["top_hashtags"]:
            print(f"{hashtag}: {count}")

        print("\nTop Engagement Posts")
        print("-" * 40)

        for post in report["top_engagement_posts"]:
            print(f"Score : {post['score']}")
            print(f"Author: {post['author']}")
            print(f"Likes : {post['likes']}")
            print(f"Comments: {post['comments']}")
            print(f"Reposts : {post['reposts']}")
            print("-" * 40)

        print("\nKeyword Distribution")
        print("-" * 40)

        for keyword, count in report["keyword_distribution"]:
            print(f"{keyword}: {count}")

        print("\nAverage Metrics")
        print("-" * 40)

        metrics = report["average_metrics"]

        print(f"Average Likes  : {metrics['avg_likes']}")
        print(f"Average Comments : {metrics['avg_comments']}")
        print(f"Average Reposts : {metrics['avg_reposts']}")

        print("\nDataset Summary")
        print("-" * 40)

        summary = report["summary"]

        print(f"Total Posts  : {summary['total_posts']}")
        print(f"Unique Authors  : {summary['unique_authors']}")
        print(f"Unique Keywords  : {summary['unique_keywords']}")
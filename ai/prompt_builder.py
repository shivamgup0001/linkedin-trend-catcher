class PromptBuilder:

    def build(self, report):

        prompt = []

        prompt.append(
            """You are an AI market analyst specializing in LinkedIn trends.

Based ONLY on the analytics provided below:

1. Write a concise executive summary.
2. Identify the dominant trends.
3. Highlight the most influential creators.
4. Explain the engagement patterns.
5. End with 3 actionable insights.

Do not invent facts.
"""
        )

        # Dataset Summary
        summary = report["summary"]

        prompt.append("## Dataset Summary")
        prompt.append(f"- Total Posts: {summary['total_posts']}")
        prompt.append(f"- Unique Authors: {summary['unique_authors']}")
        prompt.append(f"- Unique Keywords: {summary['unique_keywords']}")
        prompt.append("")

        # Top Authors
        prompt.append("## Top Authors")

        for author in report["top_authors"]:
            prompt.append(
                f"- {author['author']} ({author['posts']} posts)"
            )

        prompt.append("")

        # Top Hashtags
        prompt.append("## Top Hashtags")

        for hashtag in report["top_hashtags"]:
            prompt.append(
                f"- {hashtag['hashtag']} ({hashtag['count']} mentions)"
            )

        prompt.append("")

        # Top Engagement Posts
        prompt.append("## Top Engagement Posts")

        for post in report["top_engagement_posts"]:
            prompt.append(
                f"- {post['author']} | "
                f"Score: {post['score']} | "
                f"Likes: {post['likes']} | "
                f"Comments: {post['comments']} | "
                f"Reposts: {post['reposts']}"
            )

        prompt.append("")

        # Average Metrics
        metrics = report["average_metrics"]

        prompt.append("## Average Engagement")
        prompt.append(f"- Average Likes: {metrics['avg_likes']}")
        prompt.append(f"- Average Comments: {metrics['avg_comments']}")
        prompt.append(f"- Average Reposts: {metrics['avg_reposts']}")
        prompt.append("")

        return "\n".join(prompt)
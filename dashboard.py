"""Streamlit entry point for the read-only LinkedIn trends dashboard."""

import streamlit as st

from analytics.growth import ENGAGEMENT_WEIGHTS, MIN_RATE_WINDOW_HOURS
from dashboard_data import (
    DashboardConfigurationError,
    DashboardDataAccess,
    build_collection_run_rows,
    build_overview,
    build_post_selector_options,
    build_source_health_rows,
    build_trend_rows,
    filter_trend_rows,
    normalized_discovery_sources,
    rank_trend_rows,
)
from config.config_loader import DiscoveryConfigError, load_discovery_sources


st.set_page_config(page_title="LinkedIn Trend Catcher", layout="wide")


@st.cache_resource
def get_data_access():
    return DashboardDataAccess.from_env()


def format_time(value):
    return value.strftime("%Y-%m-%d %H:%M UTC") if value else "Unavailable"


def format_metric_time(value):
    return value.strftime("%b %d, %H:%M UTC") if value else "Unavailable"


def metric_value(value):
    return value


st.title("LinkedIn Trend Catcher")

try:
    data_access = get_data_access()
    posts = data_access.load_posts()
    snapshots = data_access.load_snapshots()
    collection_runs = data_access.load_collection_runs()
except DashboardConfigurationError as error:
    st.error(str(error))
    st.stop()
except Exception:
    st.error("MongoDB could not be read. Check the dashboard connection settings and availability.")
    st.stop()

try:
    active_sources = load_discovery_sources()
except DiscoveryConfigError as error:
    active_sources = []
    st.warning(f"Discovery configuration could not be loaded: {error}")

run_rows = build_collection_run_rows(collection_runs)
source_health_rows = build_source_health_rows(collection_runs)
post_options = build_post_selector_options(posts)
post_option_ids = [option["post_id"] for option in post_options]
post_option_labels = {
    option["post_id"]: option["label"] for option in post_options
}
if st.session_state.get("selected_post_id") not in post_option_ids:
    st.session_state.selected_post_id = post_option_ids[0] if post_option_ids else None
overview_tab, trending_tab, detail_tab, health_tab = st.tabs(
    ["Overview", "Trending Posts", "Post Detail", "Collection Health"]
)

with overview_tab:
    overview = build_overview(posts, snapshots)
    metrics = st.columns(5)
    metrics[0].metric("Total posts", overview["total_posts"])
    metrics[1].metric("Directly refreshable", overview["directly_refreshable"])
    metrics[2].metric("2+ snapshots", overview["posts_with_two_snapshots"])
    metrics[3].metric("Failed refresh", overview["failed_refreshes"])
    metrics[4].metric(
        "Latest snapshot", format_metric_time(overview["latest_snapshot_time"])
    )
    st.caption(
        "Available keywords: " + ", ".join(overview["keywords"])
        if overview["keywords"] else "Available keywords: none"
    )
    configured = ", ".join(
        f"{source.source_type.value}: {source.value}" for source in active_sources
    )
    st.caption("Active discovery sources: " + (configured or "none"))
    if run_rows:
        latest_run = run_rows[0]
        st.caption(
            f"Latest collection run: {latest_run['status']} at "
            f"{format_time(latest_run['started_at'])}"
        )

selected_from_trends = None
with trending_tab:
    st.caption(
        "Weighted growth = reactions × "
        f"{ENGAGEMENT_WEIGHTS['likes']}, comments × {ENGAGEMENT_WEIGHTS['comments']}, "
        f"reposts × {ENGAGEMENT_WEIGHTS['reposts']}."
    )
    ranking = st.radio(
        "Ranking",
        ["Momentum", "Breakout"],
        horizontal=True,
        help=(
            "Momentum favors strong absolute growth. Breakout favors growth that is "
            "large relative to the post's earlier engagement. Both scores dampen short "
            "observation windows and low-confidence histories."
        ),
    ).lower()

    authors = sorted({post.get("author") or "Unknown" for post in posts})
    keywords = sorted({post.get("keyword") or "Unknown" for post in posts})
    statuses = sorted({post.get("last_refresh_status") or "not attempted" for post in posts})
    source_types = sorted({
        source.get("type")
        for post in posts
        for source in normalized_discovery_sources(post)
        if source.get("type")
    })
    source_values = sorted({
        source.get("value")
        for post in posts
        for source in normalized_discovery_sources(post)
        if source.get("value")
    })
    filters = st.columns(5)
    selected_keywords = filters[0].multiselect("Keyword", keywords)
    selected_authors = filters[1].multiselect("Author", authors)
    selected_statuses = filters[2].multiselect("Refresh status", statuses)
    selected_source_types = filters[3].multiselect("Source type", source_types)
    selected_source_values = filters[4].multiselect("Source value", source_values)
    thresholds = st.columns(3)
    min_growth = thresholds[0].number_input(
        "Minimum weighted growth", min_value=0, value=3, step=1
    )
    max_age_days = thresholds[1].number_input(
        "Maximum post age (days)", min_value=1, value=7, step=1
    )
    observation_window = thresholds[2].number_input(
        "Minimum observation window (hours)",
        min_value=1.0,
        value=float(MIN_RATE_WINDOW_HOURS),
        step=1.0,
    )

    trend_rows = build_trend_rows(posts, snapshots, observation_window)
    trend_rows = filter_trend_rows(
        trend_rows,
        keywords=selected_keywords,
        authors=selected_authors,
        statuses=selected_statuses,
        source_types=selected_source_types,
        source_values=selected_source_values,
        min_growth=min_growth,
        max_post_age_days=max_age_days,
    )
    trend_rows = rank_trend_rows(trend_rows, ranking)

    if not trend_rows:
        st.info("No posts match these filters and observation requirements.")
    else:
        display_rows = [{
            "Author": row["author"],
            "Keyword": row["keyword"],
            "Age (hours)": metric_value(row["post_age_hours"]),
            "Reactions": metric_value(row["reactions"]),
            "Comments": metric_value(row["comments"]),
            "Reposts": metric_value(row["reposts"]),
            "Reaction growth": metric_value(row["reaction_growth"]),
            "Comment growth": metric_value(row["comment_growth"]),
            "Repost growth": metric_value(row["repost_growth"]),
            "Weighted growth": row["weighted_growth"],
            "Momentum": row["momentum_score"],
            "Breakout (%/6h)": row["breakout_score"],
            "Confidence": row["confidence"],
            "Snapshots": row["snapshot_count"],
            "Window (hours)": row["observation_hours"],
            "Last observation": row["last_observation"],
            "Refresh status": row["refresh_status"],
            "Source types": ", ".join(row["source_types"]),
            "Source values": ", ".join(row["source_values"]),
            "LinkedIn URL": row["post_url"],
        } for row in trend_rows]
        event = st.dataframe(
            display_rows,
            hide_index=True,
            width="stretch",
            on_select="rerun",
            selection_mode="single-row",
            column_config={
                "LinkedIn URL": st.column_config.LinkColumn("LinkedIn URL"),
            },
        )
        selected_rows = event.selection.rows
        if selected_rows:
            selected_from_trends = trend_rows[selected_rows[0]]["post_id"]
            st.session_state.selected_post_id = selected_from_trends
            st.caption("The selected row is shown in Post Detail.")

with detail_tab:
    if not post_options:
        st.info("No saved posts are available to inspect.")
    else:
        if selected_from_trends is not None:
            st.session_state.post_detail_selector = selected_from_trends
        elif st.session_state.get("post_detail_selector") not in post_option_ids:
            st.session_state.post_detail_selector = st.session_state.selected_post_id

        selected_post_id = st.selectbox(
            "Post",
            post_option_ids,
            key="post_detail_selector",
            format_func=lambda post_id: post_option_labels[post_id],
        )
        st.session_state.selected_post_id = selected_post_id
        post, history = data_access.post_detail(selected_post_id)
        if not post:
            st.warning("The selected post is no longer available.")
        else:
            st.subheader(post.get("author") or "Unknown author")
            post_url = post.get("post_url")
            if post_url:
                st.link_button("Open exact LinkedIn post", post_url)
                st.code(post_url, language=None)

            metadata = st.columns(4)
            metadata[0].metric("Identity source", post.get("identity_source") or "Unknown")
            metadata[1].metric("First seen", format_time(post.get("first_seen_at")))
            metadata[2].metric("Last seen", format_time(post.get("last_seen_at")))
            metadata[3].metric(
                "Refresh status", post.get("last_refresh_status") or "not attempted"
            )
            st.markdown("#### Post text")
            st.write(post.get("text") or "No post text was stored.")

            st.markdown("#### Discovery sources")
            attributed_sources = normalized_discovery_sources(post)
            if attributed_sources:
                st.dataframe(
                    [{
                        "Type": source.get("type"),
                        "Value": source.get("value"),
                        "Name": source.get("name"),
                        "URL": source.get("url"),
                    } for source in attributed_sources],
                    hide_index=True,
                    width="stretch",
                    column_config={
                        "URL": st.column_config.LinkColumn("URL"),
                    },
                )
            else:
                st.caption("No discovery attribution is stored for this post.")

            if not history:
                st.info("No engagement snapshots are available for this post.")
            else:
                chart_rows = [{
                    "observed_at": item.get("observed_at"),
                    "reactions": item.get("likes"),
                    "comments": item.get("comments"),
                    "reposts": item.get("reposts"),
                } for item in history if item.get("observed_at")]
                st.markdown("#### Engagement history")
                if chart_rows:
                    st.line_chart(
                        chart_rows,
                        x="observed_at",
                        y=["reactions", "comments", "reposts"],
                    )
                st.dataframe(
                    [{
                        "Timestamp": item.get("observed_at"),
                        "Source": item.get("source") or "Unknown",
                        "Reactions": metric_value(item.get("likes")),
                        "Comments": metric_value(item.get("comments")),
                        "Reposts": metric_value(item.get("reposts")),
                    } for item in history],
                    hide_index=True,
                    width="stretch",
                )

with health_tab:
    if not run_rows:
        st.info("No persisted collection runs are available yet.")
    else:
        latest_run = run_rows[0]
        health_metrics = st.columns(4)
        health_metrics[0].metric("Latest status", latest_run["status"])
        health_metrics[1].metric("Posts saved", latest_run["posts_saved"])
        health_metrics[2].metric(
            "Refresh success",
            f"{latest_run['refresh_successes']}/{latest_run['refresh_attempts']}",
        )
        health_metrics[3].metric("Errors", latest_run["error_count"])

        st.dataframe(
            [{
                "Started": row["started_at"],
                "Mode": row["mode"],
                "Status": row["status"],
                "Duration (s)": row["duration_seconds"],
                "Sources": row["active_sources"],
                "Candidates": row["candidates_found"],
                "Valid posts": row["valid_posts_found"],
                "Saved": row["posts_saved"],
                "Canonical URLs": row["canonical_urls_resolved"],
                "Skipped": row["skips"],
                "Warnings": row["quality_warnings"],
                "Refresh attempts": row["refresh_attempts"],
                "Refresh successes": row["refresh_successes"],
                "Refresh failures": row["refresh_failures"],
                "Errors": row["error_count"],
            } for row in run_rows],
            hide_index=True,
            width="stretch",
        )

        st.markdown("#### Per-source collection health")
        if source_health_rows:
            st.dataframe(
                [{
                    "Started": row["started_at"],
                    "Type": row["source_type"],
                    "Value": row["source_value"],
                    "Status": row["status"],
                    "Candidates": row["candidates_found"],
                    "Truncated": row["candidates_truncated"],
                    "Valid": row["valid_posts"],
                    "Saved": row["posts_saved"],
                    "Canonical URLs": row["canonical_urls_resolved"],
                    "Refreshable": row["directly_refreshable_posts"],
                    "Skips": sum(row["skips"].values()),
                    "Warnings": sum(row["quality_warnings"].values()),
                    "Errors": len(row["errors"]),
                } for row in source_health_rows],
                hide_index=True,
                width="stretch",
            )
            source_errors = [
                (row, error)
                for row in source_health_rows
                for error in row["errors"]
            ]
            if source_errors:
                st.markdown("#### Per-source errors")
                for row, error in source_errors:
                    st.error(
                        f"{row['source_type']}: {row['source_value']} · "
                        f"{error.get('stage', 'unknown')} · "
                        f"{error.get('error_type', 'Error')}: "
                        f"{error.get('message', 'No detail')}"
                    )
        else:
            st.caption("Per-source diagnostics are unavailable for legacy runs.")

        if latest_run["errors"]:
            st.markdown("#### Latest run errors")
            for error in latest_run["errors"]:
                stage = error.get("stage") or "unknown"
                error_type = error.get("error_type") or "Error"
                message = error.get("message") or "No detail"
                st.error(f"{stage} · {error_type}: {message}")

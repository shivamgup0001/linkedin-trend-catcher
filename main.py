import argparse
import time
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

from analytics.growth import MIN_RATE_WINDOW_HOURS
from analytics.trend_analyzer import TrendAnalyzer
from collector.auth import LinkedInAuth
from collector.collector import LinkedInCollector
from collector.parser import LinkedInParser
from collector.session import LinkedInSafetyStop
from collector.source_adapter import build_source_adapters
from collector.tracker import LinkedInTracker
from config.config_loader import load_discovery_sources
from database.mongo import MongoDB
from models.collection_run import CollectionRunDiagnostics


def _record_skip(diagnostics, source_diagnostics, reason, count=1):
    source_diagnostics.increment_skip(reason, count)
    for _ in range(count):
        diagnostics.discovery.increment_skip(reason)


def _record_quality_warning(diagnostics, source_diagnostics, reason):
    source_diagnostics.increment_quality_warning(reason)
    diagnostics.discovery.increment_quality_warning(reason)


def _process_candidate(
    page,
    candidate,
    source,
    db,
    parser,
    collector,
    observed_at,
    diagnostics,
    source_diagnostics,
):
    if not collector.is_post_candidate(candidate):
        _record_skip(diagnostics, source_diagnostics, "not_post")
        return

    source_diagnostics.valid_posts += 1
    diagnostics.discovery.valid_posts_found += 1
    post = parser.parse(candidate, source.value)
    copied_url = parser.resolve_post_url_from_menu(page, candidate)
    if copied_url:
        post.post_url = copied_url
        post.activity_id = parser._extract_activity_id(copied_url) or post.activity_id
        source_diagnostics.canonical_urls_resolved += 1
        diagnostics.discovery.canonical_urls_resolved += 1

    if not db.save_observation(post, observed_at, source):
        _record_skip(diagnostics, source_diagnostics, "no_identity")
        return

    source_diagnostics.posts_saved += 1
    diagnostics.discovery.posts_saved += 1
    if post.post_url and any(
        marker in post.post_url for marker in ("/feed/update/", "/posts/")
    ):
        source_diagnostics.directly_refreshable_posts += 1
        diagnostics.discovery.directly_refreshable_posts += 1
    if not post.author:
        _record_quality_warning(
            diagnostics, source_diagnostics, "missing_author"
        )
    if post.likes is None:
        _record_quality_warning(
            diagnostics, source_diagnostics, "missing_reactions"
        )


def discover_posts(
    context,
    db,
    parser,
    observed_at,
    diagnostics,
    max_candidates_per_source=5,
    sources=None,
    adapters=None,
):
    collector = LinkedInCollector()
    sources = list(sources) if sources is not None else load_discovery_sources()
    adapters = adapters if adapters is not None else build_source_adapters()

    for source in sources:
        source_diagnostics = diagnostics.begin_source(source)
        adapter = adapters.get(source.source_type)
        if adapter is None:
            error = ValueError(
                f"No discovery adapter for source type {source.source_type.value}"
            )
            diagnostics.add_source_error(source_diagnostics, "adapter_lookup", error)
            source_diagnostics.finalize(failed=True)
            print(f"Discovery failed for {source.source_type.value} {source.value}: {error}")
            continue

        page = None
        source_failed = False
        try:
            page = context.new_page()
            print(f"Discovering {source.source_type.value}: {source.value}")
            candidates = adapter.load_candidates(page, source)
            if getattr(adapter, "last_status", "ok") == "workspace_missing":
                raise RuntimeError(
                    "LinkedIn workspace was not available for this source layout"
                )

            count = candidates.count()
            source_diagnostics.candidates_found = count
            diagnostics.discovery.candidates_found += count
            process_count = min(count, max_candidates_per_source)
            truncated = count - process_count
            if truncated:
                source_diagnostics.candidates_truncated = truncated
                _record_skip(
                    diagnostics,
                    source_diagnostics,
                    "candidate_limit",
                    truncated,
                )
                print(
                    f"Found {count} candidates; processing {process_count} "
                    f"and truncating {truncated}"
                )
            else:
                print(f"Found {count} candidates")

            for index in range(process_count):
                try:
                    _process_candidate(
                        page,
                        candidates.nth(index),
                        source,
                        db,
                        parser,
                        collector,
                        observed_at,
                        diagnostics,
                        source_diagnostics,
                    )
                except LinkedInSafetyStop:
                    raise
                except Exception as error:
                    _record_skip(
                        diagnostics, source_diagnostics, "parse_error"
                    )
                    diagnostics.add_source_error(
                        source_diagnostics, "candidate_processing", error
                    )
                    error_message = source_diagnostics.errors[-1]["message"]
                    print(
                        f"Failed to process {source.source_type.value} "
                        f"candidate {index + 1}: {error_message}"
                    )
                finally:
                    if (index + 1) % 10 == 0 or index + 1 == process_count:
                        print(f"Processed {index + 1}/{process_count} candidates")
        except LinkedInSafetyStop as error:
            source_failed = True
            diagnostics.add_source_error(source_diagnostics, "authentication", error)
            raise
        except Exception as error:
            source_failed = True
            diagnostics.add_source_error(
                source_diagnostics,
                "page_open" if page is None else "load_candidates",
                error,
            )
            error_message = source_diagnostics.errors[-1]["message"]
            print(
                f"Discovery failed for {source.source_type.value} "
                f"{source.value}: {error_message}"
            )
        finally:
            if page is not None:
                try:
                    page.close()
                except Exception as error:
                    diagnostics.add_source_error(
                        source_diagnostics, "page_close", error
                    )
            source_diagnostics.finalize(failed=source_failed)

    discovery = diagnostics.discovery
    print(
        f"Discovery saved {discovery.posts_saved}; directly refreshable "
        f"{discovery.directly_refreshable_posts}; resolved "
        f"{discovery.canonical_urls_resolved} URLs"
    )
    print(f"Discovery skipped: {dict(discovery.skips_by_reason)}")
    print(
        "Discovery quality warnings: "
        f"{dict(discovery.quality_warnings_by_reason)}"
    )


def refresh_posts(
    context, db, parser, observed_at, max_track_days, refresh_limit, diagnostics
):
    targets = list(db.refresh_targets(max_track_days, refresh_limit))
    if not targets:
        print("No saved activity URLs are eligible for refresh")
        return

    tracker = LinkedInTracker(parser)
    page = context.new_page()
    refreshed = 0
    failed = 0
    try:
        for index, target in enumerate(targets, 1):
            diagnostics.refresh.attempts += 1
            try:
                metrics = tracker.refresh(page, target)
                if metrics["status"] != "ok":
                    failed += 1
                    diagnostics.refresh.record_failure(metrics["status"])
                    diagnostics.add_error(
                        "refresh",
                        f"{metrics['status']}: {metrics.get('detail') or 'no detail'}",
                    )
                    db.save_refresh_failure(
                        target["post_id"], observed_at,
                        metrics["status"], metrics.get("detail"),
                    )
                    print(
                        f"Failed to refresh {target['post_url']}: "
                        f"{metrics['status']} ({metrics.get('detail') or 'no detail'})"
                    )
                else:
                    db.save_snapshot(
                        metrics["post_id"], observed_at,
                        metrics["likes"], metrics["comments"], metrics["reposts"],
                        source="direct_refresh",
                    )
                    refreshed += 1
                    diagnostics.refresh.successes += 1
            except LinkedInSafetyStop as error:
                diagnostics.add_error("authentication", error)
                raise
            except Exception as error:
                failed += 1
                diagnostics.refresh.record_failure("exception")
                diagnostics.add_error("refresh", error)
                db.save_refresh_failure(
                    target["post_id"], observed_at, "exception", str(error)
                )
                print(f"Failed to refresh {target['post_url']}: {error}")
            if index % 10 == 0 or index == len(targets):
                print(f"Refreshed {index}/{len(targets)} saved URLs")
            page.wait_for_timeout(500)
    finally:
        page.close()
    print(f"Direct refresh saved {refreshed}; failed {failed}")


def print_trends(db, observed_at, args):
    ranked = TrendAnalyzer(db.collection, db.snapshots).top_trending(
        observed_at,
        min_window_hours=args.min_window_hours,
        min_growth=args.min_growth,
        max_post_age_days=args.max_post_age_days,
    )
    if not ranked:
        print("No posts met the trend thresholds in this cycle")
        return

    print("\nTrending by stabilized engagement momentum")
    for index, post in enumerate(ranked, 1):
        changes = post["changes"]
        print(
            f"{index}. {post['author'] or 'Unknown'} "
            f"({post['keyword']}) | momentum {post['momentum_score']} "
            f"({post['confidence']} confidence) "
            f"({post['weighted_growth']} weighted points over {post['hours']} hours) | "
            f"+{changes['likes'] or 0} reactions, "
            f"+{changes['comments'] or 0} comments, "
            f"+{changes['reposts'] or 0} reposts"
        )
        print(f"   {post['post_url'] or post['post_id']}")


def collect_once(db, args):
    observed_at = datetime.now(timezone.utc)
    diagnostics = CollectionRunDiagnostics.start(args.mode, observed_at)
    db.start_collection_run(diagnostics)
    try:
        parser = LinkedInParser()
        with sync_playwright() as playwright:
            context = LinkedInAuth(playwright, headless=args.headless).get_authenticated_context()
            context.grant_permissions(["clipboard-read", "clipboard-write"], origin="https://www.linkedin.com")
            try:
                if args.mode in {"all", "refresh"}:
                    refresh_posts(
                        context, db, parser, observed_at,
                        args.max_post_age_days, args.refresh_limit, diagnostics,
                    )
                if args.mode in {"all", "discover"}:
                    discover_posts(
                        context,
                        db,
                        parser,
                        observed_at,
                        diagnostics,
                        max_candidates_per_source=getattr(
                            args, "max_candidates_per_source", 5
                        ),
                    )
            finally:
                context.close()
        print_trends(db, observed_at, args)
    except Exception as error:
        diagnostics.add_error("collection", error)
        diagnostics.finalize(failed=True)
        db.finish_collection_run(diagnostics)
        raise
    else:
        diagnostics.finalize()
        db.finish_collection_run(diagnostics)
    return diagnostics


def parse_args():
    cli = argparse.ArgumentParser(description="Discover, refresh, and rank LinkedIn posts")
    cli.add_argument("--mode", choices=("all", "discover", "refresh"), default="all")
    cli.add_argument("--interval-hours", type=float, help="Repeat in this process; external scheduling is recommended")
    cli.add_argument("--headless", action="store_true", help="Run without a visible browser after initial login")
    cli.add_argument("--max-post-age-days", type=int, default=5)
    cli.add_argument(
        "--min-window-hours", type=float, default=MIN_RATE_WINDOW_HOURS
    )
    cli.add_argument("--min-growth", type=int, default=3, help="Minimum weighted engagement gained")
    cli.add_argument("--refresh-limit", type=int, default=15)
    cli.add_argument(
        "--max-candidates-per-source",
        type=int,
        default=5,
        help="Maximum candidates processed for each discovery source",
    )
    args = cli.parse_args()
    for name in (
        "interval_hours",
        "max_post_age_days",
        "min_window_hours",
        "min_growth",
        "refresh_limit",
        "max_candidates_per_source",
    ):
        value = getattr(args, name)
        if value is not None and value <= 0:
            cli.error(f"--{name.replace('_', '-')} must be positive")
    return args


def main():
    args = parse_args()
    db = MongoDB()
    while True:
        started = time.monotonic()
        try:
            collect_once(db, args)
        except Exception as error:
            print(f"Collection failed: {error}")
            if args.interval_hours is None:
                raise
        if args.interval_hours is None:
            break
        wait = max(0, args.interval_hours * 3600 - (time.monotonic() - started))
        print(f"Next collection in {wait / 3600:.2f} hours")
        time.sleep(wait)


if __name__ == "__main__":
    main()

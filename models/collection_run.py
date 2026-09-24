from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Union
from uuid import uuid4


MAX_RUN_ERRORS = 20
MAX_SOURCE_ERRORS = 10
MAX_ERROR_MESSAGE_LENGTH = 300


def _counter_map() -> dict[str, int]:
    return {}


def _bounded_error(stage, error, source_type=None, source_value=None):
    error_type = type(error).__name__ if isinstance(error, BaseException) else "Error"
    message = " ".join(str(error).split())[:MAX_ERROR_MESSAGE_LENGTH]
    document = {
        "stage": stage,
        "error_type": error_type,
        "message": message,
    }
    if source_type is not None:
        document["source_type"] = source_type
    if source_value is not None:
        document["source_value"] = source_value
    return document


@dataclass
class SourceDiscoveryDiagnostics:
    source_type: str
    source_value: str
    candidates_found: int = 0
    candidates_truncated: int = 0
    valid_posts: int = 0
    posts_saved: int = 0
    canonical_urls_resolved: int = 0
    directly_refreshable_posts: int = 0
    skips_by_reason: dict[str, int] = field(default_factory=_counter_map)
    quality_warnings_by_reason: dict[str, int] = field(default_factory=_counter_map)
    status: str = "running"
    errors: list[dict[str, str]] = field(default_factory=list)
    error_count: int = 0

    def increment_skip(self, reason: str, count: int = 1) -> None:
        self.skips_by_reason[reason] = self.skips_by_reason.get(reason, 0) + count

    def increment_quality_warning(self, reason: str) -> None:
        self.quality_warnings_by_reason[reason] = (
            self.quality_warnings_by_reason.get(reason, 0) + 1
        )

    def add_error(self, stage: str, error: Union[BaseException, str]) -> None:
        self.error_count += 1
        if len(self.errors) >= MAX_SOURCE_ERRORS:
            return
        self.errors.append(_bounded_error(
            stage,
            error,
            source_type=self.source_type,
            source_value=self.source_value,
        ))

    def finalize(self, failed: bool = False) -> None:
        if failed:
            self.status = "failed"
        elif self.error_count:
            self.status = "partial"
        elif self.candidates_found == 0:
            self.status = "empty"
        else:
            self.status = "completed"

    def to_document(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "source_value": self.source_value,
            "candidates_found": self.candidates_found,
            "candidates_truncated": self.candidates_truncated,
            "valid_posts": self.valid_posts,
            "posts_saved": self.posts_saved,
            "canonical_urls_resolved": self.canonical_urls_resolved,
            "directly_refreshable_posts": self.directly_refreshable_posts,
            "skips_by_reason": dict(self.skips_by_reason),
            "quality_warnings_by_reason": dict(self.quality_warnings_by_reason),
            "status": self.status,
            "error_count": self.error_count,
            "errors": list(self.errors),
        }


@dataclass
class DiscoveryDiagnostics:
    candidates_found: int = 0
    valid_posts_found: int = 0
    posts_saved: int = 0
    directly_refreshable_posts: int = 0
    canonical_urls_resolved: int = 0
    skips_by_reason: dict[str, int] = field(default_factory=_counter_map)
    quality_warnings_by_reason: dict[str, int] = field(default_factory=_counter_map)

    def increment_skip(self, reason: str) -> None:
        self.skips_by_reason[reason] = self.skips_by_reason.get(reason, 0) + 1

    def increment_quality_warning(self, reason: str) -> None:
        self.quality_warnings_by_reason[reason] = (
            self.quality_warnings_by_reason.get(reason, 0) + 1
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "candidates_found": self.candidates_found,
            "valid_posts_found": self.valid_posts_found,
            "posts_saved": self.posts_saved,
            "directly_refreshable_posts": self.directly_refreshable_posts,
            "canonical_urls_resolved": self.canonical_urls_resolved,
            "skips_by_reason": dict(self.skips_by_reason),
            "quality_warnings_by_reason": dict(self.quality_warnings_by_reason),
        }


@dataclass
class RefreshDiagnostics:
    attempts: int = 0
    successes: int = 0
    failures: int = 0
    failures_by_status: dict[str, int] = field(default_factory=_counter_map)

    def record_failure(self, status: str) -> None:
        self.failures += 1
        self.failures_by_status[status] = self.failures_by_status.get(status, 0) + 1

    def to_document(self) -> dict[str, Any]:
        return {
            "attempts": self.attempts,
            "successes": self.successes,
            "failures": self.failures,
            "failures_by_status": dict(self.failures_by_status),
        }


@dataclass
class CollectionRunDiagnostics:
    mode: str
    observed_at: datetime
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    run_id: str = field(default_factory=lambda: str(uuid4()))
    active_discovery_sources: list[dict[str, str]] = field(default_factory=list)
    source_diagnostics: list[SourceDiscoveryDiagnostics] = field(default_factory=list)
    discovery: DiscoveryDiagnostics = field(default_factory=DiscoveryDiagnostics)
    refresh: RefreshDiagnostics = field(default_factory=RefreshDiagnostics)
    errors: list[dict[str, str]] = field(default_factory=list)
    error_count: int = 0
    finished_at: Optional[datetime] = None
    status: str = "running"
    duration_seconds: Optional[float] = None

    @classmethod
    def start(cls, mode: str, observed_at: datetime) -> "CollectionRunDiagnostics":
        return cls(
            mode=mode,
            observed_at=observed_at,
            started_at=observed_at,
        )

    def begin_source(self, source) -> SourceDiscoveryDiagnostics:
        summary = {
            "type": source.source_type.value,
            "value": source.value,
        }
        if source.name is not None:
            summary["name"] = source.name
        if source.url is not None:
            summary["url"] = source.url
        self.active_discovery_sources.append(summary)
        diagnostics = SourceDiscoveryDiagnostics(
            source_type=source.source_type.value,
            source_value=source.value,
        )
        self.source_diagnostics.append(diagnostics)
        return diagnostics

    def add_error(
        self,
        stage: str,
        error: Union[BaseException, str],
        source_type: Optional[str] = None,
        source_value: Optional[str] = None,
    ) -> None:
        self.error_count += 1
        if len(self.errors) >= MAX_RUN_ERRORS:
            return
        self.errors.append(_bounded_error(
            stage,
            error,
            source_type=source_type,
            source_value=source_value,
        ))

    def add_source_error(
        self,
        source_diagnostics: SourceDiscoveryDiagnostics,
        stage: str,
        error: Union[BaseException, str],
    ) -> None:
        source_diagnostics.add_error(stage, error)
        self.add_error(
            stage,
            error,
            source_type=source_diagnostics.source_type,
            source_value=source_diagnostics.source_value,
        )

    def finalize(self, failed: bool = False, finished_at: Optional[datetime] = None) -> None:
        self.finished_at = finished_at or datetime.now(timezone.utc)
        elapsed = (self.finished_at - self.started_at).total_seconds()
        self.duration_seconds = max(0.0, round(elapsed, 3))
        if failed:
            self.status = "failed"
        elif (
            self.error_count
            or self.discovery.skips_by_reason.get("parse_error", 0)
            or self.refresh.failures
        ):
            self.status = "partial"
        else:
            self.status = "completed"

    def to_document(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "mode": self.mode,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "observed_at": self.observed_at,
            "status": self.status,
            "duration_seconds": self.duration_seconds,
            "active_discovery_sources": list(self.active_discovery_sources),
            "source_diagnostics": [
                source.to_document() for source in self.source_diagnostics
            ],
            "discovery": self.discovery.to_document(),
            "refresh": self.refresh.to_document(),
            "error_count": self.error_count,
            "errors": list(self.errors),
        }

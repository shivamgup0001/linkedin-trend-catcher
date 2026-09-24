from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlsplit, urlunsplit

import yaml

from config.discovery_source import DiscoverySource, DiscoverySourceType


DEFAULT_CONFIG_PATH = Path(__file__).parent / "keywords.yaml"
SOURCE_SECTIONS = {
    "keywords": DiscoverySourceType.KEYWORD,
    "hashtags": DiscoverySourceType.HASHTAG,
    "creators": DiscoverySourceType.CREATOR,
    "companies": DiscoverySourceType.COMPANY,
}


class DiscoveryConfigError(ValueError):
    pass


def load_discovery_sources(
    config_path: Optional[Union[str, Path]] = None,
) -> List[DiscoverySource]:
    """Load, validate, normalize, and deduplicate enabled discovery sources."""
    path = Path(config_path) if config_path is not None else DEFAULT_CONFIG_PATH
    data = _read_yaml(path)

    unknown_root_fields = set(data) - {"discovery", "keywords"}
    if unknown_root_fields:
        names = ", ".join(sorted(unknown_root_fields))
        raise DiscoveryConfigError(f"Unsupported top-level config field(s): {names}")
    if "discovery" in data and "keywords" in data:
        raise DiscoveryConfigError(
            "Use either the structured 'discovery' config or the legacy 'keywords' list, not both"
        )

    if "discovery" in data:
        sources = _parse_structured_config(data["discovery"])
    else:
        sources = _parse_legacy_config(data.get("keywords", []))

    unique = []
    seen = set()
    for source in sources:
        if source.deduplication_key in seen:
            continue
        seen.add(source.deduplication_key)
        unique.append(source)
    return unique


def load_keywords(config_path: Optional[Union[str, Path]] = None) -> List[str]:
    """Return enabled keyword values for the existing keyword search workflow."""
    return [
        source.value
        for source in load_discovery_sources(config_path)
        if source.source_type == DiscoverySourceType.KEYWORD
    ]


def _read_yaml(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as config_file:
            data = yaml.safe_load(config_file)
    except (OSError, yaml.YAMLError) as error:
        raise DiscoveryConfigError(f"Could not load discovery config {path}: {error}") from error

    if data is None:
        return {}
    if not isinstance(data, dict):
        raise DiscoveryConfigError("Discovery config must be a YAML mapping")
    return data


def _parse_legacy_config(entries: Any) -> List[DiscoverySource]:
    if not isinstance(entries, list):
        raise DiscoveryConfigError("Legacy 'keywords' must be a list")

    sources = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, str):
            raise DiscoveryConfigError(f"keywords[{index}] must be a string")
        value = _normalize_text(entry, f"keywords[{index}]")
        sources.append(DiscoverySource(DiscoverySourceType.KEYWORD, value))
    return sources


def _parse_structured_config(discovery: Any) -> List[DiscoverySource]:
    if not isinstance(discovery, dict):
        raise DiscoveryConfigError("'discovery' must be a mapping")

    unknown_sections = set(discovery) - set(SOURCE_SECTIONS)
    if unknown_sections:
        names = ", ".join(sorted(unknown_sections))
        raise DiscoveryConfigError(f"Unsupported discovery source section(s): {names}")

    sources = []
    for section, source_type in SOURCE_SECTIONS.items():
        entries = discovery.get(section, [])
        if not isinstance(entries, list):
            raise DiscoveryConfigError(f"discovery.{section} must be a list")
        for index, entry in enumerate(entries):
            label = f"discovery.{section}[{index}]"
            source = _parse_source(source_type, entry, label)
            if source is not None:
                sources.append(source)
    return sources


def _parse_source(source_type: DiscoverySourceType, entry: Any, label: str):
    if not isinstance(entry, dict):
        raise DiscoveryConfigError(f"{label} must be a mapping")

    enabled = entry.get("enabled", True)
    if not isinstance(enabled, bool):
        raise DiscoveryConfigError(f"{label}.enabled must be true or false")

    if source_type in {DiscoverySourceType.KEYWORD, DiscoverySourceType.HASHTAG}:
        _reject_unknown_fields(entry, {"value", "enabled"}, label)
        value = _normalize_text(entry.get("value"), f"{label}.value")
        if source_type == DiscoverySourceType.HASHTAG:
            value = value.lstrip("#")
            if not value or not re.fullmatch(r"\w+", value):
                raise DiscoveryConfigError(
                    f"{label}.value must be a hashtag without spaces or punctuation"
                )
        source = DiscoverySource(source_type, value)
    else:
        url_field = "profile_url" if source_type == DiscoverySourceType.CREATOR else "page_url"
        _reject_unknown_fields(entry, {"name", url_field, "enabled"}, label)
        name = _normalize_text(entry.get("name"), f"{label}.name")
        url = _normalize_linkedin_url(entry.get(url_field), source_type, f"{label}.{url_field}")
        source = DiscoverySource(source_type, name, name=name, url=url)

    return source if enabled else None


def _normalize_text(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise DiscoveryConfigError(f"{label} must be a string")
    normalized = re.sub(r"\s+", " ", value).strip()
    if not normalized:
        raise DiscoveryConfigError(f"{label} cannot be empty")
    return normalized


def _normalize_linkedin_url(
    value: Any,
    source_type: DiscoverySourceType,
    label: str,
) -> str:
    url = _normalize_text(value, label)
    parts = urlsplit(url)
    hostname = (parts.hostname or "").lower()
    if parts.scheme not in {"http", "https"} or hostname not in {"linkedin.com", "www.linkedin.com"}:
        raise DiscoveryConfigError(f"{label} must be a LinkedIn URL")

    segments = [segment for segment in parts.path.split("/") if segment]
    expected_prefix = "in" if source_type == DiscoverySourceType.CREATOR else "company"
    if len(segments) != 2 or segments[0].lower() != expected_prefix:
        expected = f"https://www.linkedin.com/{expected_prefix}/example/"
        raise DiscoveryConfigError(f"{label} must match {expected}")

    path = f"/{expected_prefix}/{segments[1]}/"
    return urlunsplit(("https", "www.linkedin.com", path, "", ""))


def _reject_unknown_fields(entry: Dict[str, Any], allowed, label: str) -> None:
    unknown = set(entry) - allowed
    if unknown:
        names = ", ".join(sorted(unknown))
        raise DiscoveryConfigError(f"Unsupported field(s) in {label}: {names}")

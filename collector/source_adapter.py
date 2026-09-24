"""Discovery-source adapter contract and default collector registry."""

from collector.collector import LinkedInCollector
from collector.company_source import CompanySourceCollector
from collector.creator_source import CreatorSourceCollector
from collector.hashtag_source import HashtagSourceCollector
from collector.scroller import LinkedInScroller
from collector.search import LinkedInSearch
from collector.source_page import load_scrolled_candidates
from config.discovery_source import DiscoverySource, DiscoverySourceType


class KeywordSourceCollector:
    """Adapt the existing keyword search workflow to ``load_candidates``."""

    def __init__(self, searcher=None, scroller=None, collector=None):
        self.searcher = searcher or LinkedInSearch()
        self.scroller = scroller or LinkedInScroller()
        self.collector = collector or LinkedInCollector()

    def load_candidates(self, page, source: DiscoverySource, candidate_limit=None):
        if getattr(source, "source_type", None) != DiscoverySourceType.KEYWORD:
            raise ValueError("KeywordSourceCollector requires a KEYWORD source")
        self.searcher.search(page, source.value)
        return load_scrolled_candidates(
            page,
            self.scroller,
            self.collector,
            candidate_limit=candidate_limit,
        )


def build_source_adapters():
    """Return one sequential candidate-loader adapter for every supported type."""
    return {
        DiscoverySourceType.KEYWORD: KeywordSourceCollector(),
        DiscoverySourceType.HASHTAG: HashtagSourceCollector(),
        DiscoverySourceType.CREATOR: CreatorSourceCollector(),
        DiscoverySourceType.COMPANY: CompanySourceCollector(),
    }

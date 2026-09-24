from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple


class DiscoverySourceType(str, Enum):
    KEYWORD = "keyword"
    HASHTAG = "hashtag"
    CREATOR = "creator"
    COMPANY = "company"


@dataclass(frozen=True)
class DiscoverySource:
    source_type: DiscoverySourceType
    value: str
    name: Optional[str] = None
    url: Optional[str] = None

    @property
    def deduplication_key(self) -> Tuple[str, str]:
        identity = self.url.casefold() if self.url else self.value.casefold()
        return self.source_type.value, identity

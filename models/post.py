from dataclasses import dataclass
from typing import Optional
from datetime import datetime
from dataclasses import field

@dataclass
class Post:
    keyword: str

    activity_id: Optional[str] = None
    author: Optional[str] = None
    author_url: Optional[str] = None
    text: Optional[str] = None

    posted_at: Optional[str] = None
    scraped_at: datetime = field(default_factory=datetime.utcnow)

    likes: Optional[int] = None
    comments: Optional[int] = None
    reposts: Optional[int] = None

    post_url: Optional[str] = None

    has_image: bool = False
    has_video: bool = False
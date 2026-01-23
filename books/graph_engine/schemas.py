from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class BookNode:
    id: str
    title: str
    author: str
    rating: Optional[int] = None

    subjects: List[str] = field(default_factory=list)
    cover_url: Optional[str] = None
    openlibrary_id: Optional[str] = None

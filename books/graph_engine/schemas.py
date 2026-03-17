from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class BookNode:
    id: str               # Unique key: "Title::Author"
    title: str
    author: str
    rating: Optional[int] = None  # Goodreads rating (1–5), or None if not rated

    # OpenLibrary data
    subjects: List[str] = field(default_factory=list)
    award_slugs: List[str] = field(default_factory=list)  # e.g. ["hugo_award", "nebula_award"]
    cover_url: Optional[str] = None
    openlibrary_id: Optional[str] = None
    description: Optional[str] = None
    page_count: Optional[int] = None
    first_publish_year: Optional[int] = None
    ol_ratings_average: Optional[float] = None

    # Inventaire data
    inventaire_uri: Optional[str] = None

    # Goodreads data
    goodreads_id: Optional[str] = None

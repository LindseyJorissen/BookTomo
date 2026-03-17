import re
import networkx as nx

_GENERIC_SUBJECTS = {
    "fiction", "nonfiction", "non-fiction", "literature", "books",
    "novel", "novels", "prose literature", "general",
    "english literature", "american literature", "american fiction", "english fiction",
    "essays", "anthologies", "collections",
    # Age/format labels with no genre content
    "juvenile", "adult", "children", "large type books", "large print",
    # Overly vague location/school references
    "schools", "school",
}

# Subjects matching any of these patterns are skipped entirely.
_SKIP_RE = re.compile(
    r"^series:"                           # Goodreads series tags: series:Harry_Potter
    r"|^franchise:"                       # Goodreads franchise tags
    r"|^genre:"                           # Goodreads genre tags
    r"|\(fictitious character"            # character names
    r"|\(imaginary"                       # imaginary organisations
    r"|prize\s+winner"                    # award labels
    r"|smarties"                          # specific award brands
    r"|,\s*strips"                        # "comic books, strips, etc"
    r"|\blarge type\b"                    # publishing format
    r"|\bstrip\b.*comic"
    r"|\bseries$",                        # "The Bridgertons series"
    re.I,
)


def _expand_subject(subject: str) -> list:
    """Normalize a raw subject string into a list of clean genre tags.

    Handles:
    - OL '-- Fiction' / '-- Qualifier' suffixes        → stripped
    - OL ', fiction' / ', general' comma suffixes      → stripped
    - Trailing ' fiction' word                         → stripped
    - Compound comma-separated categories              → split
      e.g. "Fiction, Romance, Historical, Regency"    → ["Romance", "Historical", "Regency"]
      e.g. "Young adult fiction, vampires"            → ["Young adult", "Vampires"]
    - series: tags, character names, award labels      → filtered
    - Mostly non-ASCII / foreign language subjects     → filtered
    """
    if _SKIP_RE.search(subject):
        return []

    # Filter mostly non-ASCII (foreign language)
    ascii_count = sum(1 for c in subject if ord(c) < 128)
    if len(subject) > 4 and ascii_count / len(subject) < 0.80:
        return []

    # Strip OL "-- qualifier" suffix  e.g. "Wizards -- Fiction"
    s = re.sub(r"\s+--\s+.*$", "", subject).strip()

    # Strip trailing ", fiction" / ", juvenile fiction" / ", general" / ", etc"
    s = re.sub(r",\s*(?:juvenile\s+)?fiction\s*$", "", s, flags=re.I).strip()
    s = re.sub(r",\s*(?:etc\.?|general)\s*$", "", s, flags=re.I).strip()

    # Strip trailing standalone " fiction" word  e.g. "Fantasy fiction" → "Fantasy"
    s = re.sub(r"\s+fiction\s*$", "", s, flags=re.I).strip()

    if not s:
        return []

    # Split compound comma-separated categories when each part is ≤ 4 words
    # e.g. "Fiction, Romance, Historical, Regency" or "Young adult, Vampires"
    if "," in s:
        parts = [p.strip() for p in s.split(",")]
        if all(1 <= len(p.split()) <= 4 for p in parts if p):
            result = []
            for p in parts:
                p = re.sub(r"\s+fiction\s*$", "", p, flags=re.I).strip()
                if p:
                    result.append(p)
            return result if result else [s]

    return [s]


def build_genre_graph(books):
    """Build a NetworkX graph for genre-based community detection.

    Subjects are expanded and normalised via _expand_subject so that e.g.
    "Fantasy fiction", "Fantasy", and "Young adult fiction, fantasy" all
    produce the same "Fantasy" node, allowing books to cluster together.

    Used by detect_communities() so the Reading Universe shows taste clusters.
    """
    G = nx.Graph()
    for book in books:
        book_node = f"book::{book.id}"
        G.add_node(book_node, type="book", title=book.title, author=book.author, rating=book.rating)

        seen_subjects: set = set()
        for subject in book.subjects:
            for raw_norm in _expand_subject(subject):
                if not raw_norm or raw_norm.lower() in _GENERIC_SUBJECTS or len(raw_norm) < 3:
                    continue
                # Normalise to title case so "fantasy", "Fantasy", "FANTASY" → same node
                norm = raw_norm.strip().title()
                key = norm.lower()
                if key in seen_subjects:
                    continue
                seen_subjects.add(key)
                subject_node = f"subject::{norm}"
                if not G.has_node(subject_node):
                    G.add_node(subject_node, type="subject", name=norm)
                G.add_edge(book_node, subject_node, weight=1.0)

    return G


def build_author_graph(books):
    """Build a NetworkX graph from a list of BookNode objects.

    Node types:
      - book::     A read book (title, author, rating)
      - author::   An author (connects books by the same writer)
      - subject::  An OpenLibrary subject (only for books with fetched data)

    Edge weights:
      - Book → author:  1.0, scaled by a rating multiplier (max 1.2 at rating 5)
      - Book → subject: 0.8
    """
    G = nx.Graph()

    for book in books:
        book_node = f"book::{book.id}"
        author_node = f"author::{book.author}"

        G.add_node(book_node, type="book", title=book.title, author=book.author, rating=book.rating)
        G.add_node(author_node, type="author", name=book.author)

        for subject in book.subjects:
            subject_node = f"subject::{subject}"
            if not G.has_node(subject_node):
                G.add_node(subject_node, type="subject", name=subject)
            G.add_edge(book_node, subject_node, weight=0.8)

        # Rating 3 = neutral (1.0), rating 5 = maximum boost (1.2)
        rating_multiplier = 1.0
        if book.rating:
            rating_multiplier = min(1.0 + ((book.rating - 3) * 0.1), 1.2)

        G.add_edge(book_node, author_node, weight=1.0 * rating_multiplier)

    return G

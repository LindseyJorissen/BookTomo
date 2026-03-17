from .schemas import BookNode
from . import state
from books.openlibrary.client import fetch_work_data, fetch_cover_for_read_book
from books.inventaire.client import fetch_cover as inventaire_fetch_cover
from books.google_books.client import fetch_categories as fetch_gb_categories

# Books beyond this index are fetched in the background thread (background.py).
MAX_COVER_LOOKUPS = 10

# Genre/subject terms to exclude — children's and adult content
_BLOCKED_GENRE_TERMS = {
    "children", "children's", "picture book", "picture books",
    "children's fiction", "children's stories", "children's literature",
    "childrens fiction", "childrens stories", "childrens literature",
    "erotica", "erotic fiction", "erotic literature", "adult fiction",
    "sexuality", "sex", "pornography",
}

# Substrings that flag a tag as blocked
_BLOCKED_SUBSTRINGS = ("children's", "childrens", "erotica", "erotic")


def _is_blocked_genre(tag: str) -> bool:
    """Return True if this genre/subject tag is on the blocked list."""
    lower = tag.lower().strip()
    if lower in _BLOCKED_GENRE_TERMS:
        return True
    return any(sub in lower for sub in _BLOCKED_SUBSTRINGS) or lower == "picture books"


def _apply_gb_genres(book: BookNode) -> None:
    """Merge Google Books genre categories into book.subjects.

    Results are stored permanently in CachedBook.google_books_genres and also
    appended to book.subjects for use in clustering and display.
    Case-insensitive duplicates are skipped.
    """
    existing = {s.lower() for s in book.subjects}
    genres = fetch_gb_categories(book.title, book.author)
    new = [g for g in genres if g.lower() not in existing and not _is_blocked_genre(g)]
    if new:
        book.subjects = book.subjects + new


def _apply_ol_data(book: BookNode, ol_data: dict) -> None:
    """Copy OpenLibrary fields from a fetch_work_data result dict onto a BookNode."""
    if not ol_data:
        return
    if not book.cover_url and ol_data.get("cover_url"):
        book.cover_url = ol_data["cover_url"]
    if not book.subjects and ol_data.get("subjects"):
        book.subjects = [s for s in ol_data["subjects"] if not _is_blocked_genre(s)]
    if not book.award_slugs and ol_data.get("award_slugs"):
        book.award_slugs = ol_data["award_slugs"]
    if not book.openlibrary_id and ol_data.get("openlibrary_id"):
        book.openlibrary_id = ol_data["openlibrary_id"]
    if not book.description and ol_data.get("description"):
        book.description = ol_data["description"]
    if not book.page_count and ol_data.get("page_count"):
        book.page_count = ol_data["page_count"]
    if not book.first_publish_year and ol_data.get("first_publish_year"):
        book.first_publish_year = ol_data["first_publish_year"]
    if not book.ol_ratings_average and ol_data.get("ol_ratings_average"):
        book.ol_ratings_average = ol_data["ol_ratings_average"]


def extract_books_from_df(df):
    """Convert a Goodreads DataFrame into a list of BookNode objects.

    For the first MAX_COVER_LOOKUPS books, metadata is fetched immediately.
    The remaining books have their covers loaded by the background thread.

    Fetch strategy (all results are DB-cached with a 30-day TTL):
      1. OpenLibrary work data — subjects, awards, cover, description, metadata
      2. OpenLibrary cover search — cover only, if still missing
      3. Inventaire — cover only, as last resort
    """
    books = []
    total_rows = len(df)
    state.UPLOAD_PROGRESS["total"] = total_rows
    state.UPLOAD_PROGRESS["current"] = 0
    state.UPLOAD_PROGRESS["phase"] = "fetching"

    for i, (_, row) in enumerate(df.iterrows()):
        title = row.get("Title")
        author = row.get("Author")
        if not title or not author:
            continue

        rating = row.get("My Rating")
        if rating == 0:
            rating = None

        # Goodreads book ID — cast via int→str to strip any ".0" from pandas float parsing
        raw_gid = row.get("Book Id")
        goodreads_id = str(int(raw_gid)) if raw_gid and str(raw_gid) not in ("", "nan") else None

        book = BookNode(
            id=f"{title}::{author}",
            title=title,
            author=author,
            rating=rating,
            goodreads_id=goodreads_id,
        )

        if i < MAX_COVER_LOOKUPS:
            _apply_ol_data(book, fetch_work_data(title, author, is_read=True))
            if not book.cover_url:
                book.cover_url = fetch_cover_for_read_book(title, author, is_read=True)
            if not book.cover_url:
                book.cover_url = inventaire_fetch_cover(title, author)
            _apply_gb_genres(book)

        books.append(book)
        state.UPLOAD_PROGRESS["current"] = i + 1

    return books

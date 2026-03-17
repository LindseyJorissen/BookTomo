from django.db import models


class CachedBook(models.Model):
    """
    Permanent database store for book metadata fetched from OpenLibrary and Inventaire.
    Records are never expired — each book is fetched once and kept forever.
    """

    # --- Lookup key ---
    title = models.CharField(max_length=500)
    author = models.CharField(max_length=300)

    # --- External IDs ---
    openlibrary_id = models.CharField(max_length=200, blank=True)
    inventaire_uri = models.CharField(max_length=200, blank=True)

    # --- Cover ---
    cover_url = models.URLField(max_length=1000, blank=True)

    # --- Metadata (populated by OpenLibrary) ---
    subjects = models.JSONField(default=list)       # Clean subject tags (award:* filtered out)
    award_slugs = models.JSONField(default=list)    # OL award slugs e.g. ["hugo_award", "nebula_award"]
    description = models.TextField(blank=True)
    page_count = models.IntegerField(null=True, blank=True)
    publisher = models.CharField(max_length=300, blank=True)
    published_date = models.CharField(max_length=20, blank=True)
    first_publish_year = models.IntegerField(null=True, blank=True)
    isbn_13 = models.CharField(max_length=13, blank=True)
    isbn_10 = models.CharField(max_length=10, blank=True)
    language = models.CharField(max_length=10, blank=True)

    # --- Popularity / ratings (from OL) ---
    ol_ratings_average = models.FloatField(null=True, blank=True)
    ol_ratings_count = models.IntegerField(null=True, blank=True)
    want_to_read_count = models.IntegerField(null=True, blank=True)

    # --- Google Books genres (permanent, keyed by title+author) ---
    google_books_genres = models.JSONField(default=list)   # e.g. ["Fantasy", "Science Fiction"]
    google_books_fetched = models.BooleanField(default=False)

    # --- Read status ---
    is_read = models.BooleanField(default=False)  # True = in user's Goodreads library

    # --- Fetch tracking ---
    openlibrary_fetched = models.BooleanField(default=False)
    inventaire_fetched = models.BooleanField(default=False)

    class Meta:
        unique_together = [("title", "author")]
        indexes = [
            models.Index(fields=["title", "author"]),
        ]



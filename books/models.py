from django.db import models
from django.utils import timezone


class CachedBook(models.Model):
    """
    Persistent database cache for book metadata fetched from OpenLibrary and Inventaire.
    Records are considered fresh for 30 days; stale records are re-fetched on the next request.
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

    # --- Cache tracking ---
    openlibrary_fetched = models.BooleanField(default=False)
    inventaire_fetched = models.BooleanField(default=False)
    fetched_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("title", "author")]
        indexes = [
            models.Index(fields=["title", "author"]),
        ]

    def is_stale(self):
        return (timezone.now() - self.fetched_at).days > 30

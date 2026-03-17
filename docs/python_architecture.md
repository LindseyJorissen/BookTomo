# BookTomo — Python Architecture

## 1. Project Overview

BookTomo is a "Spotify Wrapped for books" application that analyses a user's Goodreads reading history and presents:

- **Reading statistics** — total books, pages, ratings, reading cadence, publication-year patterns, and book-length distributions.
- **A network-based recommendation graph** — an interactive, force-directed visualisation that shows relationships between the books you have read and suggests new ones based on shared authors, genres, awards, and publication eras.

The backend is a Django application that exposes a REST-like JSON API consumed by a React frontend. All heavy computation (graph building, OpenLibrary API calls, cover fetching) happens server-side; the frontend is purely a display layer.

---

## 2. Project Structure

```
BookTomo/
├── backend/                      # Django project settings
│   ├── settings.py               # Database, cache, CORS, installed apps
│   ├── urls.py                   # Root URL routing (mounts /api/ prefix)
│   ├── wsgi.py / asgi.py
│   └── __init__.py
│
├── books/                        # Main Django application
│   ├── models.py                 # CachedBook — persistent book-metadata cache
│   ├── views.py                  # All API endpoint handlers
│   ├── urls.py                   # /api/* URL patterns
│   │
│   ├── graph_engine/             # Core data and graph logic
│   │   ├── schemas.py            # BookNode dataclass
│   │   ├── state.py              # In-memory global state (BOOK_NODES, GRAPH, progress)
│   │   ├── extract.py            # Goodreads CSV → BookNode list
│   │   ├── builder.py            # BookNode list → NetworkX graph
│   │   └── visualize_interactive.py  # NetworkX graph → PyVis HTML
│   │
│   ├── openlibrary/              # OpenLibrary API client
│   │   ├── client.py             # Search, metadata, cover, and recommendation fetchers
│   │   └── background.py         # Daemon thread for deferred cover loading
│   │
│   └── inventaire/               # Inventaire API client (cover / book fallback)
│       └── client.py
│
├── frontend/                     # React application (separate dev server)
├── docs/                         # This documentation
├── manage.py
├── requirements.txt
└── db.sqlite3                    # SQLite cache database
```

### Module responsibilities

| Module | Responsibility |
|---|---|
| `graph_engine/schemas.py` | Defines the `BookNode` dataclass — the canonical in-memory representation of one read book. |
| `graph_engine/state.py` | Holds three module-level globals: `BOOK_NODES`, `GRAPH`, and `UPLOAD_PROGRESS`. These survive the lifetime of the Django process and are shared across requests. |
| `graph_engine/extract.py` | Converts a pandas DataFrame (from a Goodreads CSV) into a list of `BookNode` objects, fetching OpenLibrary/Inventaire data for the first batch synchronously. |
| `graph_engine/builder.py` | Turns a `BookNode` list into a `networkx.Graph` containing book, author, and subject nodes with weighted edges. |
| `graph_engine/visualize_interactive.py` | Accepts a NetworkX graph and a focus-book node ID, builds a PyVis `Network` object, injects custom JavaScript for hover cards, click tooltips, and load animation, and returns the result as an HTML string. |
| `openlibrary/client.py` | All calls to the OpenLibrary REST API. Results are cached in both the Django DB (`CachedBook`, 30-day TTL) and Django's file-based cache (24-hour TTL). |
| `openlibrary/background.py` | A daemon thread that fetches covers and metadata for the books beyond the first 10 after a CSV upload, updating `state.BOOK_NODES` in place. |
| `inventaire/client.py` | Fallback source for covers and book lists when OpenLibrary returns nothing. |
| `books/views.py` | All HTTP handlers. Orchestrates the above modules and returns JSON or HTML. |

---

## 3. Goodreads CSV Processing

**Entry point:** `POST /api/upload_goodreads/` → `views.upload_goodreads`

### Steps

1. **Read CSV** — `pandas.read_csv(file)` parses the uploaded file into a DataFrame.
2. **Filter to read books** — rows where `Exclusive Shelf == "read"` are kept. If the column is absent the full DataFrame is used.
3. **Progress initialisation** — `state.UPLOAD_PROGRESS` is set to `{phase: "parsing", current: 0, total: 0}` so the frontend polling endpoint has something to return immediately.
4. **Extract BookNodes** — `extract_books_from_df(read_df)` (see §3.1).
5. **Build graph** — `build_author_graph(read_books)` (see §5).
6. **Statistics** — date columns are parsed and all stat helpers are called.
7. **Background thread** — `load_remaining_covers()` is started as a daemon thread.
8. **Response** — a single JSON object containing all stats and the initial book list.

### 3.1 `extract_books_from_df` — CSV → BookNode list

Located in `books/graph_engine/extract.py`.

For each row in the DataFrame:

```python
BookNode(
    id    = f"{title}::{author}",   # unique key used throughout the system
    title = row["Title"],
    author = row["Author"],
    rating = row["My Rating"] or None,
)
```

**For the first 10 books only** (constant `MAX_COVER_LOOKUPS`), metadata is fetched synchronously via a three-step strategy:

1. `fetch_work_data(title, author)` — full OpenLibrary work metadata (subjects, award slugs, cover URL, description, page count, first-publish year, ratings average).
2. `fetch_cover_for_read_book(title, author)` — cover-only OL search, used as a fallback if step 1 returned no cover.
3. `inventaire_fetch_cover(title, author)` — Inventaire cover search, last resort.

Progress is updated after each row so the frontend progress bar moves smoothly.

### Key CSV fields extracted

| CSV column | BookNode field |
|---|---|
| `Title` | `title` |
| `Author` | `author` |
| `My Rating` | `rating` (0 → None) |
| fetched via OL | `subjects`, `award_slugs`, `cover_url`, `description`, `page_count`, `first_publish_year`, `ol_ratings_average` |

---

## 4. Statistics Engine

Located in `books/views.py` (module-level helpers called from `upload_goodreads`).

### `compute_cadence(date_series)`

Accepts a pandas Series of date-read timestamps. Drops nulls, deduplicates, sorts chronologically, then computes the gaps (in days) between consecutive dates.

Returns `None` when fewer than two dates are present, otherwise:

```json
{
  "avg_days": 12.4,
  "median_days": 9,
  "fastest_days": 1,
  "slowest_days": 87,
  "first_finished": "2015-03-01",
  "last_finished": "2025-11-15"
}
```

### `compute_stats(subset)`

Accepts a DataFrame subset and returns:

```json
{
  "total_books": 148,
  "total_pages": 54320,
  "avg_rating": 3.87,
  "top_author": "Brandon Sanderson"
}
```

Ratings of 0 are excluded from the average (Goodreads stores "not rated" as 0).

### `compute_book_lengths(subset)`

Computes page-count statistics from the `Number of Pages` column:

- `average_pages` — integer mean
- `longest_book` — title, author, page count of the highest-page-count book
- `histogram` — counts bucketed into five ranges: 0–200, 200–300, 300–400, 400–500, 500+

### Scatter data

Two scatter datasets are produced:

- `scatter_publication_vs_read_all` — all books: `{pub_year, read_value}` where `read_value` is the year the book was read.
- `scatter_publication_vs_read_year` — current year only: `{pub_year, read_value}` where `read_value` is the month number (1–12).

---

## 5. Network Graph Generation

Located in `books/graph_engine/builder.py`.

### `build_author_graph(books)`

Constructs a `networkx.Graph` from a list of `BookNode` objects.

**Node types:**

| Node ID pattern | `type` attribute | Represents |
|---|---|---|
| `book::Title::Author` | `"book"` | A book the user has read |
| `author::Name` | `"author"` | An author |
| `subject::Genre` | `"subject"` | An OpenLibrary subject/genre |

**Edge weights:**

| Edge | Default weight | Notes |
|---|---|---|
| book → subject | 0.8 | Fixed for all genre connections |
| book → author | 1.0 × rating_multiplier | Multiplier = `min(1.0 + (rating-3)*0.1, 1.2)` — 5-star books have slightly stronger author edges |

Genre nodes are only added when a book has OpenLibrary subject data (i.e., it was in the first 10 books or was processed by the background thread).

---

## 6. Recommendation System

Recommendations are generated on demand when the frontend requests a graph for a specific book via `GET /api/graph/<book_id>/`.

Located in `books/views.py → book_graph_view`.

### How it works

The function operates on a **copy** of `state.GRAPH` so the global graph is never mutated. It then adds recommendation nodes and edges to this copy before handing it to PyVis for rendering.

Four recommendation strategies run in sequence, each adding `unread=True` book nodes:

#### 1. Author-based

```python
fetch_unread_books_by_author(author, read_titles, limit=8)
# Falls back to inventaire if OL returns nothing
```

Reason string: `"Same author as {Author}"`

#### 2. Genre-based

Genres for the selected book are fetched from OpenLibrary (`fetch_work_data`). They are ranked by a **genre score** — the sum of ratings of the user's read books that share that genre. The top 3 genres are used.

For each top genre:
```python
fetch_books_by_subject(genre, limit=5)
# Falls back to inventaire
```

Reason string: `"Shares genre: {genre}"`

#### 3. Award-based

If the selected book has award slugs in its OL metadata, the top 2 awards are used:
```python
fetch_books_by_award(award_slug, limit=5)
```

Reason string: `"Also won the {Award Name}"`

#### 4. Era-based

The book's publication decade is used to find popular contemporaries:
```python
fetch_books_by_era(decade_start, primary_genre, limit=5)
```

Reason string: `"Popular from the {decade}s"`

### Deduplication

All recommendation books are checked against:
- `read_titles` — normalised titles of books already in the user's library
- `already_added` — books already added as recommendations in this request

`normalize_title(title)` strips parentheticals (e.g. subtitles in brackets) and colons before comparison.

### Scoring for "Best Recommendation"

The `GET /api/best_recommendation/` endpoint ranks candidate books from the user's top 3 genres:

```
score = genre_match_count * 1          (from genre_counts[genre])
      + 5  (if author is already read)
```

The candidate with the highest score is returned along with 2–3 plain-English reason strings.

### Graph filters

`book_graph_view` accepts optional query parameters:

| Parameter | Effect |
|---|---|
| `genres` (repeatable) | Only add recommendations linked to the listed genres |
| `authors` (repeatable) | Only add unread-book nodes whose author is in the list |
| `year_min` / `year_max` | Only add era nodes whose decade falls within the range |

---

## 7. API Endpoints

All endpoints are mounted under `/api/` (defined in `backend/urls.py` and `books/urls.py`).

### `POST /api/upload_goodreads/`

Upload a Goodreads CSV export.

**Request:** `multipart/form-data` with field `file`.

**Response:**
```json
{
  "overall": { "total_books": 148, "total_pages": 54320, "avg_rating": 3.87, "top_author": "...", "cadence": {...} },
  "this_year": { ... },
  "yearly_books": { "2019": 24, "2020": 31, ... },
  "monthly_books": { "1": 3, "2": 5, ... },
  "scatter_publication_vs_read_all": [{ "pub_year": 1999, "read_value": 2023 }, ...],
  "scatter_publication_vs_read_year": [...],
  "book_lengths": { "overall": { "average_pages": 367, ... }, "this_year": { ... } },
  "oldest_pub_year": 1813,
  "books": [{ "id": "Title::Author", "title": "...", "author": "...", "cover_url": "..." }, ...]
}
```

---

### `GET /api/upload_progress/`

Polling endpoint for the loading-bar while an upload is in progress.

**Response:**
```json
{ "phase": "fetching", "current": 23, "total": 148 }
```

Phases: `parsing` → `fetching` → `building` → `done`

---

### `GET /api/graph/<book_id>/`

Generate and return an interactive HTML graph for the given book.

`book_id` format: `book::Title::Author` (URL-encoded).

Optional query parameters: `genres`, `authors`, `year_min`, `year_max`.

**Response:** `text/html` — a self-contained PyVis page with embedded vis.js and custom JavaScript.

---

### `GET /api/covers/`

Return updated cover URLs for all books in the current session (polled by the frontend every 3 seconds while covers are loading in the background).

**Response:**
```json
{ "covers": [{ "id": "Title::Author", "cover_url": "https://..." }, ...] }
```

---

### `GET /api/book_details/<book_id>/`

Return metadata and similar books for the sidebar detail panel.

`book_id` format: `Title::Author` (URL-encoded).

**Response:**
```json
{
  "id": "The Name of the Wind::Patrick Rothfuss",
  "title": "The Name of the Wind",
  "author": "Patrick Rothfuss",
  "rating": 5,
  "pages": 662,
  "genres": ["Fantasy", "Fiction", "Adventure"],
  "cover_url": "https://...",
  "description": "...",
  "similar": [
    { "id": "...", "title": "...", "author": "...", "cover_url": "...", "reason": "Same author" },
    ...
  ]
}
```

---

### `GET /api/best_recommendation/`

Return the single highest-scoring recommendation for the user's library.

**Response:**
```json
{
  "title": "The Way of Kings",
  "author": "Brandon Sanderson",
  "cover_url": "https://...",
  "reasons": [
    "Same genre cluster as 12 books you liked",
    "Same author as books you enjoyed"
  ],
  "score": 17
}
```

---

### `GET /api/filter_options/`

Return the genres, authors, and year range available for graph filtering.

**Response:**
```json
{
  "genres": ["Fantasy", "Fiction", "Science Fiction", ...],
  "authors": ["Brandon Sanderson", "J.K. Rowling", ...],
  "year_min": 1954,
  "year_max": 2023
}
```

---

## 8. Caching Strategy

BookTomo uses two caching layers to avoid redundant API calls to OpenLibrary and Inventaire.

### Database cache (`CachedBook` model)

Stores full book metadata per `(title, author)` pair with a 30-day TTL (`is_stale()` checks `updated_at`). Covers all fields: subjects, awards, description, page count, cover URL, OL ratings.

### Django file-based cache

Used for bulk search results (subject searches, award book lists, era book lists). Cache keys are MD5 hashes of the query string. TTL: 24 hours.

### Frontend polling

After a CSV upload, the frontend polls `GET /api/covers/` every 3 seconds. The background thread updates `state.BOOK_NODES` in place as covers are fetched; the polling endpoint reads directly from this shared state.

### Goodreads genre store (`BookGenres` model)

A **permanent, never-expiring** SQLite table that stores crowd-sourced genre tags scraped from Goodreads. Unlike `CachedBook` (30-day TTL), `BookGenres` records are written once and kept forever — genre classification for a book rarely changes.

---

## 10. Goodreads Genre Scraping

### Why

OpenLibrary subjects are often sparse or overly generic ("Fiction", "American literature"). Goodreads crowd-sourced genre shelves ("Fantasy", "Young Adult", "Historical Romance") are far more specific and are the tags users actually recognise.

### Data flow

1. The Goodreads CSV export includes a **`Book Id`** column (integer). `extract_books_from_df` reads this and stores it on `BookNode.goodreads_id`.
2. **On upload** (first `MAX_COVER_LOOKUPS` books): `_apply_gr_genres(book)` is called immediately after OpenLibrary/Inventaire fetching.
3. **In background** (remaining books): `load_remaining_covers()` calls `_apply_gr_genres(book)` after the cover fetch steps.
4. `_apply_gr_genres` calls `fetch_genres(goodreads_id)` from `books/goodreads/scraper.py`, then appends any new genres to `book.subjects` (case-insensitive dedup).

### Scraping mechanism (`books/goodreads/scraper.py`)

Goodreads pages are built with Next.js. All page data — including genre tags — is embedded in a `<script id="__NEXT_DATA__">` JSON block. No JavaScript rendering is needed; a plain `requests.get` is sufficient.

The JSON contains an Apollo GraphQL cache. Genre tags live under keys like `"Book:12345"` → `bookGenres` → `[{"genre": {"__ref": "Genre:fantasy"}}]`, with genre names resolved at the top level under `"Genre:fantasy"` → `{"name": "Fantasy"}`.

```python
# Simplified extraction logic
for value in apollo_state.values():
    for bg in value.get("bookGenres", []):
        ref = bg["genre"]["__ref"]
        genres.append(apollo_state[ref]["name"])
```

A `1.5 s` delay is applied between requests (`_DELAY`). Since this is personal use only, this is sufficient to avoid overloading Goodreads.

### Permanent storage

Results are saved to `BookGenres` via `update_or_create(goodreads_id=...)`. On subsequent uploads (or re-uploads of the same library), the DB lookup short-circuits the scrape entirely — genres are never re-fetched.

### Enrichment result

`book.subjects` ends up as a merged list from three sources:

| Source | Example values |
| --- | --- |
| OpenLibrary | `"Fantasy fiction"`, `"Magic -- Fiction"` |
| Goodreads crowd shelves | `"Fantasy"`, `"Young Adult"`, `"Magic School"` |

This richer subject list directly improves cluster labelling in `universe.py`.

## 9. Community Detection & Reading Universe

### Overview

After the graph is built, BookTomo uses **NetworkX community detection** to cluster books into reading taste groups. These clusters power the "Reading Universe" view — a high-level overview graph where each node represents a reading cluster rather than an individual book.

### Algorithm

`books/graph_engine/universe.py` uses `networkx.algorithms.community.greedy_modularity_communities`, a fast greedy algorithm that maximises graph modularity (a measure of how well-defined cluster boundaries are). It operates on the full heterogeneous graph (book + author + subject + award + era nodes), so clusters naturally reflect shared themes, genres, and authors.

```python
from networkx.algorithms.community import greedy_modularity_communities

raw = list(greedy_modularity_communities(graph))
# Each raw community is a frozenset of node IDs
```

### Cluster metadata

Each detected community is converted to a structured dict:

| Field | Description |
| --- | --- |
| `id` | Stable string key (`"cluster::N"`) |
| `name` | Human-readable reading-taste label (see *Cluster label generation* below) |
| `book_count` | Number of `BookNode` objects in the cluster |
| `book_nodes` | List of graph node IDs for book nodes in the cluster |
| `representative_book` | Node ID of the book with the highest degree — used as click target |
| `top_genres` | Up to 3 most common meaningful subjects in the cluster |
| `explanation_signals` | Up to 3 human-readable bullet strings explaining the grouping |
| `tooltip_html` | Pre-rendered HTML tooltip shown on hover |

Clusters with no book nodes are discarded. Results are sorted descending by `book_count`.

### Cluster label generation

`_generate_cluster_label(analysis, index)` turns raw genre/author data into a readable reading-taste label using the following priority order:

1. **`"{Author} Universe"`** — if a single author accounts for more than 60 % of books in the cluster (detected via `dominant_author` in `_analyze_cluster`).
2. **`"{Genre1} & {Genre2}"`** — if two meaningful subjects are present (generic subjects like "Fiction" or "Literature" are filtered out by `_GENERIC_SUBJECTS`).
3. **`"{Genre1}"`** — single meaningful subject.
4. **`"Reading Cluster {n}"`** — fallback when no subject data is available.

Subject names are first cleaned by `_clean_subject`, which strips trailing OpenLibrary qualifiers like `"-- Fiction"` or `"-- Juvenile fiction"` before filtering.

### Cluster explanation signals

`_generate_explanation_signals(analysis)` builds up to 3 bullet-point strings shown inside the hover tooltip:

- Primary genre (e.g. `"Fantasy fiction genre"`)
- Secondary genre used as themes signal (e.g. `"Historical fiction themes"`)
- Author dominance or repeated author (e.g. `"Strong J.K. Rowling author connections"`)

### Universe graph rendering

`render_universe_graph(clusters, graph)` builds a PyVis graph where:

- **Nodes** represent clusters, sized proportionally to `book_count` (range: 28–90 px). Node labels show the cluster name and book count.
- **Edges** connect clusters that share at least one genre/subject node in the original graph, indicating overlapping reading interests.
- **HTML tooltips** show the cluster name, book count, explanation signals, and up to 3 example book titles.
- **Click handler** fires `window.parent.postMessage({type: "CLUSTER_CLICK", representativeBook, clusterName, topGenres}, "*")` so the React parent can transition to the ego-graph view for that cluster's representative book.
- **Legend** — a fixed overlay in the bottom-left corner explains node size, colour coding, and click behaviour.

### Caching

`state.COMMUNITIES` stores the detected clusters after CSV upload so community detection (which traverses the full graph) only runs once per session. `universe_graph_view` reads from the cache and only re-runs detection if the cache is empty.

### Fallback

If fewer than 2 clusters are detected (e.g. the user has only a handful of books), the universe endpoint returns a plain HTML message explaining that more books are needed, rather than rendering a meaningless single-cluster graph.

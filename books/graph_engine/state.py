# Global application state — shared across all views within one server process.
# Note: with multiple concurrent users, they would overwrite each other's data.
# Intended for single-user / personal use only.

BOOK_NODES = []            # List of BookNode objects after CSV upload
WANT_TO_READ_NODES = []   # List of BookNode objects from user's to-read / currently-reading shelf
GRAPH = None               # NetworkX graph built from BOOK_NODES
COMMUNITIES = None         # Cached community clusters (list of dicts from universe.py)

# Progress tracking for the upload flow.
# phase: "idle" | "parsing" | "fetching" | "building" | "done"
UPLOAD_PROGRESS = {"phase": "idle", "current": 0, "total": 0}

# Incremented whenever the background thread finishes rebuilding communities.
# Frontend polls for changes to know when to reload the universe graph.
UNIVERSE_VERSION = 0

# Progress of the background cover/subject fetching thread.
# done=True once the thread has finished processing all books.
BACKGROUND_PROGRESS = {"current": 0, "total": 0, "done": True}

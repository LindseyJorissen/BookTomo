import { useState, useEffect, useRef } from "react";
import "./App.css";
import YearlyBookChart from "./YearlyBookChart";
import PublicationVsReadChart from "./PublicationVsReadChart";
import BookLengthChart from "./BookLengthChart";
import BookGraph from "./components/BookGraph";

const API = "http://127.0.0.1:8000/api";

function StarRating({ rating }) {
  if (!rating) return null;
  return (
    <span className="star-rating">
      {[1, 2, 3, 4, 5].map(i => (
        <span key={i} style={{ color: i <= rating ? "#d4af7a" : "#ccc" }}>★</span>
      ))}
    </span>
  );
}

function SimilarityBar({ score }) {
  if (score == null) return null;
  const pct = Math.round(score * 100);
  return (
    <div className="similarity-row">
      <span className="similarity-label">Similarity</span>
      <div className="similarity-bar-wrap">
        <div className="similarity-bar-fill" style={{ width: `${pct}%` }} />
      </div>
      <span className="similarity-value">{score.toFixed(2)}</span>
    </div>
  );
}

function App() {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);
  const [showTutorial, setShowTutorial] = useState(false);
  const [showMenu, setShowMenu] = useState(false);
  const [activeView, setActiveView] = useState("stats");
  const [timeView, setTimeView] = useState("overall");
  const [selectedBook, setSelectedBook] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState({ phase: "idle", current: 0, total: 0 });

  // Graph state
  const [graphMode, setGraphMode] = useState("universe"); // "universe" | "book"
  const [graphLoading, setGraphLoading] = useState(false);
  const [universeVersion, setUniverseVersion] = useState(0);

  // Book detail panel
  const [showDetailPanel, setShowDetailPanel] = useState(false);
  const [bookDetail, setBookDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [panelMode, setPanelMode] = useState("read"); // "read" | "recommendation"

  // Background processing progress
  const [bgProgress, setBgProgress] = useState({ current: 0, total: 0, done: true });

  // Best recommendation
  const [bestRec, setBestRec] = useState(null);

  // Graph controls
  const [minSimilarity, setMinSimilarity] = useState(0.5);
  const [hideStartedSeries, setHideStartedSeries] = useState(false);

  // Collapsible book list
  const [bookListCollapsed, setBookListCollapsed] = useState(true);

  const menuRef = useRef(null);
  const fileInputRef = useRef(null);
  const bookLengths = stats?.book_lengths?.[timeView];

  // ── Graph URL ──────────────────────────────────────────────────────────────
  const getGraphUrl = () => {
    if (graphMode === "universe") return `${API}/universe_graph/?v=${universeVersion}`;
    if (!selectedBook) return `${API}/universe_graph/`;
    const base = `http://localhost:8000/api/graph/${encodeURIComponent("book::" + selectedBook.id)}`;
    const params = new URLSearchParams();
    params.set("min_similarity", minSimilarity);
    if (hideStartedSeries) params.set("hide_started_series", "true");
    return `${base}?${params.toString()}`;
  };

  // Trigger loading indicator whenever the graph URL changes
  const graphUrl = getGraphUrl();
  useEffect(() => {
    if (graphUrl) setGraphLoading(true);
  }, [graphUrl]);

  // ── postMessage listener (from graph iframes) ──────────────────────────────
  useEffect(() => {
    if (!stats) return;

    const handleMessage = (e) => {
      if (!e.data?.type) return;

      if (e.data.type === "CLUSTER_CLICK") {
        // Universe cluster clicked → switch to ego graph of representative book
        const repId = e.data.representativeBook?.replace("book::", "");
        const book = stats.books.find(b => b.id === repId);
        if (book) setSelectedBook(book);
        setGraphMode("book");
        setGraphLoading(true);
      } else if (e.data.type === "BOOK_CLICK") {
        // Graph recommendation node clicked → open detail panel
        setBookDetail({
          title: e.data.title,
          author: e.data.author,
          cover_url: e.data.cover_url,
          reason: e.data.reason,
          signals: e.data.signals || [],
          similarity_score: e.data.similarity_score,
        });
        setPanelMode("recommendation");
        setShowDetailPanel(true);
      }
    };

    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [stats]);

  // ── Book detail panel (sidebar click) ─────────────────────────────────────
  const openBookDetails = async (book) => {
    setSelectedBook(book);
    setGraphMode("book");
    setGraphLoading(true);
    setPanelMode("read");
    setShowDetailPanel(true);
    setDetailLoading(true);
    setBookDetail(null);
    try {
      const res = await fetch(`${API}/book_details/${encodeURIComponent(book.id)}/`);
      if (res.ok) setBookDetail(await res.json());
    } catch (_) {}
    setDetailLoading(false);
  };

  // ── Upload ─────────────────────────────────────────────────────────────────
  const handleUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    e.target.value = "";
    const formData = new FormData();
    formData.append("file", file);
    setIsUploading(true);
    try {
      const res = await fetch(`${API}/upload_goodreads/`, { method: "POST", body: formData });
      if (!res.ok) throw new Error(`Server error: ${res.status}`);
      const data = await res.json();
      setStats(data);
      setSelectedBook(null);
      setGraphMode("universe");
      setActiveView("stats");
      setTimeView("overall");
      setUniverseVersion(0);
      setBgProgress({ current: 0, total: 0, done: false });
      setError(null);
    } catch (err) {
      setError(err.message);
      setStats(null);
    } finally {
      setIsUploading(false);
    }
  };

  // ── Side-effects on stats load ─────────────────────────────────────────────
  useEffect(() => {
    if (!stats) return;

    fetch(`${API}/best_recommendation/`)
      .then(r => r.ok ? r.json() : null)
      .then(data => data && !data.error && setBestRec(data))
      .catch(() => {});
  }, [stats]);

  // Poll for cover updates and universe version
  useEffect(() => {
    if (!stats) return;
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${API}/covers/`);
        const data = await res.json();
        // Update covers
        if (data.covers?.length) {
          setStats(prev => ({
            ...prev,
            books: prev.books.map(book => {
              const found = data.covers.find(c => c.id === book.id);
              return found ? { ...book, cover_url: found.cover_url } : book;
            }),
          }));
        }
        // Auto-reload universe when background thread finishes rebuilding communities
        if (data.universe_version != null) {
          setUniverseVersion(prev => {
            if (data.universe_version > prev) {
              if (graphMode === "universe") setGraphLoading(true);
              return data.universe_version;
            }
            return prev;
          });
        }
        // Track background processing progress
        if (data.background_progress != null) {
          setBgProgress(data.background_progress);
        }
      } catch (_) {}
    }, 3000);
    return () => clearInterval(interval);
  }, [stats, graphMode]);

  // Poll upload progress
  useEffect(() => {
    if (!isUploading) return;
    setUploadProgress({ phase: "parsing", current: 0, total: 0 });
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${API}/upload_progress/`);
        setUploadProgress(await res.json());
      } catch (_) {}
    }, 400);
    return () => clearInterval(interval);
  }, [isUploading]);

  // Close menu on outside click
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) setShowMenu(false);
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // ── Progress helpers ───────────────────────────────────────────────────────
  const getProgressPct = () => {
    const { phase, current, total } = uploadProgress;
    if (phase === "parsing")  return 2;
    if (phase === "fetching") return total > 0 ? Math.round(2 + (current / total) * 88) : 2;
    if (phase === "building") return 92;
    if (phase === "done")     return 100;
    return 0;
  };

  const getProgressLabel = () => {
    const { phase, current, total } = uploadProgress;
    if (phase === "parsing")  return "Reading your library…";
    if (phase === "fetching") return total > 0 ? `Fetching book data… (${current} of ${total})` : "Fetching book data…";
    if (phase === "building") return "Building your reading graph…";
    if (phase === "done")     return "Almost there…";
    return "Crunching your books…";
  };

  const getReadingOverTimeText = () => {
    const s = stats[timeView];
    if (!s) return "";
    return timeView === "overall"
      ? `Across your entire reading history, you've finished ${s.total_books} books. The chart above shows how your reading ebbs and flows over time.`
      : `So far this year, you've finished ${s.total_books} books. Your reading activity varies across the months.`;
  };

  const getPublicationTimingText = () => {
    if (!stats) return "";
    const oldest = stats.oldest_pub_year;
    return timeView === "overall"
      ? `Your reading spans a wide range of publication years, reaching back well beyond recent releases. ${oldest ? `The oldest book you've read was published in ${oldest}.` : ""}`
      : `This year's reading includes books from different publication periods. ${oldest ? `The oldest one dates back to ${oldest}.` : ""}`;
  };

  // Parse recommendation reason into structured signals for the panel
  const parseReasonSignals = (reason) => {
    if (!reason) return [];
    if (reason.startsWith("Same author")) {
      return [{ label: "Common author network", value: reason.replace("Same author as ", "") + " cluster" }];
    }
    if (reason.startsWith("Shares genre:")) {
      return [{ label: "Shared genres", value: reason.replace("Shares genre: ", "") }];
    }
    if (reason.startsWith("Also won")) {
      return [{ label: "Award match", value: reason.replace("Also won the ", "") }];
    }
    if (reason.startsWith("Popular from")) {
      return [{ label: "Same era", value: reason.replace("Popular from the ", "") }];
    }
    return [{ label: "Reason", value: reason }];
  };

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div style={activeView === "suggestions" && stats ? { padding: "2rem", display: "flex", flexDirection: "column", height: "100vh", boxSizing: "border-box", overflow: "hidden" } : { padding: "2rem" }}>

      <input ref={fileInputRef} type="file" onChange={handleUpload} style={{ display: "none" }} />

      {/* Upload loading overlay */}
      {isUploading && (
        <div className="loading-overlay">
          <div className="loading-card neu-card">
            <p>{getProgressLabel()}</p>
            <div className="loading-bar">
              <div className="loading-bar-fill" style={{ width: `${getProgressPct()}%` }} />
            </div>
            <p style={{ fontSize: "0.9rem", opacity: 0.7, marginTop: "0.5rem" }}>
              This can take a moment for large libraries
            </p>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="app-header">
        <div className="app-title-block">
          <h1>BookTomo</h1>
          <p className="app-subtitle">Your reading universe</p>
        </div>
        {stats ? (
          <div className="top-tabs">
            <button className={`upload-button neu-card ${activeView === "stats" ? "neu-pressed" : ""}`} onClick={() => setActiveView("stats")}>Stats</button>
            <button className={`upload-button neu-card ${activeView === "suggestions" ? "neu-pressed" : ""}`} onClick={() => setActiveView("suggestions")}>Suggestions</button>
          </div>
        ) : <div />}
        <div className="menu-wrapper" ref={menuRef}>
          <button className="menu-btn neu-card" onClick={() => setShowMenu(v => !v)} aria-label="Open menu">⋮</button>
          {showMenu && (
            <div className="menu-dropdown neu-card">
              <button className="menu-item" onClick={() => { setShowMenu(false); fileInputRef.current.click(); }}>
                {stats ? "Upload new CSV" : "Upload CSV"}
              </button>
              <button className="menu-item" onClick={() => { setShowTutorial(v => !v); setShowMenu(false); }}>
                How to export from Goodreads
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Background loading banner */}
      {stats && !bgProgress.done && bgProgress.total > 0 && (
        <div className="bg-progress-banner">
          <span className="bg-progress-text">
            Enriching your library in the background… {bgProgress.current} of {bgProgress.total} books processed
          </span>
          <div className="bg-progress-bar">
            <div
              className="bg-progress-fill"
              style={{ width: `${Math.round((bgProgress.current / bgProgress.total) * 100)}%` }}
            />
          </div>
        </div>
      )}

      {/* Tutorial */}
      <div className={`tutorial-panel ${showTutorial ? "open" : ""}`}>
        <h3>How to export from Goodreads</h3>
        <ol>
          <li>Log in to Goodreads</li>
          <li>Click <strong>My Books</strong></li>
          <li>Scroll down and click <strong>Import and Export</strong> under tools</li>
          <li>Click <strong>Export Library</strong></li>
          <li>Download the CSV and upload it here</li>
        </ol>
      </div>

      {/* Empty state */}
      {!stats && (
        <div className="empty-state">
          <p>Upload your Goodreads CSV to see your reading stats!</p>
          <button className="upload-cta neu-card" onClick={() => fileInputRef.current.click()}>Upload CSV</button>
        </div>
      )}

      {error && <p style={{ color: "red" }}>Error: {error}</p>}

      {/* ── Stats view ── */}
      {activeView === "stats" && stats && (
        <div className="stats-container">
          <div className="stats-box neu-card">
            <div className="stats-box-header" style={{ gridRow: "span 2" }}>
              <div className="view-toggle">
                <button className={`upload-button small neu-card ${timeView === "overall" ? "neu-pressed" : ""}`} onClick={() => setTimeView("overall")}>Overall</button>
                <button className={`upload-button small neu-card ${timeView === "this_year" ? "neu-pressed" : ""}`} onClick={() => setTimeView("this_year")}>This Year</button>
              </div>
            </div>
            <h2>{timeView === "overall" ? "All-time stats" : "This Year's stats"}</h2>
            <p>Total books: {stats[timeView].total_books}</p>
            <p>Total pages: {stats[timeView].total_pages}</p>
            <p>Average rating: {stats[timeView].avg_rating}</p>
            <p>Top author: {stats[timeView].top_author || "N/A"}</p>
            <hr />
            <h3>Reading cadence</h3>
            <p>Avg days per book: {stats[timeView].cadence?.avg_days}</p>
            <p>Median days per book: {stats[timeView].cadence?.median_days}</p>
            <p>Fastest gap: {stats[timeView].cadence?.fastest_days} days</p>
            <p>Longest gap: {stats[timeView].cadence?.slowest_days} days</p>
          </div>

          <div className="chart-box neu-card">
            {timeView === "overall" && <YearlyBookChart yearlyData={stats.yearly_books} type="year" />}
            {timeView === "this_year" && <YearlyBookChart yearlyData={stats.monthly_books} type="month" />}
          </div>

          <div className="chart-box neu-card">
            {timeView === "overall" && <PublicationVsReadChart data={stats.scatter_publication_vs_read_all} type="year" />}
            {timeView === "this_year" && <PublicationVsReadChart data={stats.scatter_publication_vs_read_year} type="month" />}
          </div>

          <div className="info-box neu-card">
            <h3>Reading over time</h3>
            <p>{getReadingOverTimeText()}</p>
          </div>

          <div className="info-box neu-card">
            <h3>When you read books</h3>
            <p>{getPublicationTimingText()}</p>
          </div>

          <div className="right-grid">
            <div className="chart-stack">
              <div className="chart-box neu-card">
                {bookLengths?.histogram && <BookLengthChart data={bookLengths.histogram} />}
              </div>
              <div className="info-box2 neu-card">
                {bookLengths && (
                  <>
                    <p>On average, your books are about <strong>{bookLengths.average_pages}</strong> pages long.</p>
                    {bookLengths.longest_book && (() => {
                      const { title, author, pages } = bookLengths.longest_book;
                      return <p>Your longest finished book was <strong>{title}</strong> by {author}, at {pages} pages.</p>;
                    })()}
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Suggestions view ── */}
      {activeView === "suggestions" && stats && (
        <div className="suggestions-view">
          {/* Best Recommendation card */}
          {bestRec && (
            <div className="best-rec-card neu-card">
              <div className="best-rec-label">Best recommendation for you</div>
              <div className="best-rec-content">
                {bestRec.cover_url && <img src={bestRec.cover_url} alt={bestRec.title} className="best-rec-cover" />}
                <div className="best-rec-info">
                  <strong className="best-rec-title">{bestRec.title}</strong>
                  <div className="best-rec-author">{bestRec.author}</div>
                  <ul className="best-rec-reasons">
                    {bestRec.reasons?.map((r, i) => <li key={i}>{r}</li>)}
                  </ul>
                </div>
              </div>
            </div>
          )}

          <div
            className="suggestions-layout"
            style={{ gridTemplateColumns: bookListCollapsed ? "58px 1fr" : "280px 1fr" }}
          >
            {/* Left: book list (collapsible) */}
            <div className={`book-list neu-card ${bookListCollapsed ? "collapsed" : ""}`}>
              <div className="book-list-header">
                {!bookListCollapsed && <h3>Your Read Books</h3>}
                {bookListCollapsed && (
                  <span className="book-list-collapsed-label">Your Read Books</span>
                )}
                <button
                  className="collapse-toggle-btn"
                  onClick={() => setBookListCollapsed(v => !v)}
                  title={bookListCollapsed ? "Expand" : "Collapse"}
                >
                  {bookListCollapsed ? "›" : "‹"}
                </button>
              </div>
              {!bookListCollapsed && (
                <div className="book-list-scroll">
                  {stats.books.map((book) => (
                    <button
                      key={book.id}
                      className={`book-item ${selectedBook?.id === book.id ? "active" : ""}`}
                      onClick={() => openBookDetails(book)}
                    >
                      <img src={book.cover_url || "/placeholder-book.png"} alt={book.title} className="book-cover" loading="lazy" />
                      <div className="book-meta">
                        <strong>{book.title}</strong>
                        <div className="book-author">{book.author}</div>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Right: graph */}
            <div className="graph-container neu-card">
              {/* Graph header */}
              <div className="graph-header">
                {graphMode === "universe" ? (
                  <>
                    <h2 className="graph-title">Your Reading Universe</h2>
                    <p className="graph-subtitle">Your reading taste map. Books are grouped into clusters based on shared authors, genres, and themes. Click a cluster to explore it.</p>
                    {!bgProgress.done && bgProgress.total > 0 && (
                      <p className="universe-loading-notice">
                        <img src="/hourglass.svg" className="universe-hourglass" alt="" />
                        Still enriching your library ({bgProgress.current}/{bgProgress.total} books) — clusters will improve once complete.
                      </p>
                    )}
                  </>
                ) : (
                  <div className="graph-header-book">
                    <button className="back-to-universe-btn" onClick={() => { setGraphMode("universe"); setGraphLoading(true); }}>
                      ← Reading Universe
                    </button>
                    <div>
                      <h2 className="graph-title">{selectedBook?.title || "Recommendations"}</h2>
                      <p className="graph-subtitle">Discover recommendations based on shared authors, genres, and themes.</p>
                    </div>
                  </div>
                )}
              </div>

              {/* Controls (book mode only) */}
              {graphMode === "book" && (
                <div className="graph-controls neu-card">
                  <div className="graph-control-row">
                    <label className="graph-control-label">Similarity to read books</label>
                    <span className="graph-control-hint">Broader</span>
                    <input
                      type="range"
                      className="similarity-slider"
                      min={0.5}
                      max={0.95}
                      step={0.05}
                      value={minSimilarity}
                      onChange={e => setMinSimilarity(parseFloat(e.target.value))}
                    />
                    <span className="graph-control-hint">Closer</span>
                    <span className="graph-control-value">{Math.round(minSimilarity * 100)}%</span>
                  </div>
                  <div className="graph-control-row">
                    <label className="graph-control-label">Hide started series</label>
                    <button
                      className={`series-toggle ${hideStartedSeries ? "active" : ""}`}
                      onClick={() => setHideStartedSeries(v => !v)}
                    >
                      {hideStartedSeries ? "On" : "Off"}
                    </button>
                  </div>
                </div>
              )}

              {/* Legend (book mode only) */}
              {graphMode === "book" && (
                <div className="graph-legend neu-card">
                  <div className="legend-item"><span className="legend-dot read"></span><span>Read book</span></div>
                  <div className="legend-item"><span className="legend-dot unread"></span><span>Recommendation</span></div>
                  <div className="legend-item"><span className="legend-dot author"></span><span>Author</span></div>
                </div>
              )}

              {/* Graph iframe */}
              <div style={{ flex: 1, minHeight: 0, position: "relative" }}>
                {graphLoading && (
                  <div className="graph-loading-overlay">
                    <div className="graph-loading-card neu-card">
                      <p className="graph-loading-label">
                        {graphMode === "universe" ? "Mapping your reading universe…" : "Building your graph…"}
                      </p>
                      <div className="loading-bar">
                        <div className="loading-bar-fill loading-bar-indeterminate" />
                      </div>
                    </div>
                  </div>
                )}
                <iframe
                  key={graphUrl}
                  src={graphUrl}
                  onLoad={() => setGraphLoading(false)}
                  style={{ position: "absolute", inset: 0, width: "100%", height: "100%", border: "none", borderRadius: "16px" }}
                  title="Book Graph"
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Book detail panel (slide-in from right) ── */}
      <div className={`book-detail-panel ${showDetailPanel ? "open" : ""}`}>
        <div className="detail-panel-header">
          <button className="detail-close-btn" onClick={() => setShowDetailPanel(false)}>✕</button>
        </div>

        {detailLoading && <p style={{ padding: "1rem", opacity: 0.6 }}>Loading…</p>}

        {bookDetail && !detailLoading && (
          <div className="detail-panel-body">

            {/* Hero cover */}
            {bookDetail.cover_url && (
              <img src={bookDetail.cover_url} alt={bookDetail.title} className="detail-cover-hero" />
            )}

            <h2 className="detail-title">{bookDetail.title}</h2>
            <div className="detail-author">{bookDetail.author}</div>

            {/* Recommendation explanation */}
            {panelMode === "recommendation" ? (
              <div className="rec-explanation">
                <div className="rec-explanation-heading">Why this recommendation?</div>
                <SimilarityBar score={bookDetail.similarity_score} />
                <div className="rec-signals">
                  {(bookDetail.signals?.length > 0
                    ? bookDetail.signals
                    : parseReasonSignals(bookDetail.reason)
                  ).map((signal, i) => (
                    <div key={i} className="rec-signal-row">
                      <span className="rec-signal-label">{signal.label}</span>
                      <span className="rec-signal-value">• {signal.value}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              /* Read book details */
              <>
                {bookDetail.rating && (
                  <div className="detail-row">
                    <span className="detail-label">Rating</span>
                    <StarRating rating={bookDetail.rating} />
                  </div>
                )}
                {bookDetail.pages && (
                  <div className="detail-row">
                    <span className="detail-label">Pages</span>
                    <span>{bookDetail.pages}</span>
                  </div>
                )}
                {bookDetail.genres?.length > 0 && (
                  <div className="detail-row">
                    <span className="detail-label">Genres</span>
                    <div className="detail-genres">
                      {bookDetail.genres.map(g => <span key={g} className="genre-tag">{g}</span>)}
                    </div>
                  </div>
                )}
                {bookDetail.similar?.length > 0 && (
                  <div className="detail-similar">
                    <h3>Similar books</h3>
                    {bookDetail.similar.map(b => (
                      <button key={b.id} className="similar-book-item" onClick={() => openBookDetails(b)}>
                        {b.cover_url && <img src={b.cover_url} alt={b.title} className="similar-cover" />}
                        <div>
                          <div className="similar-title">{b.title}</div>
                          <div className="similar-reason">{b.reason}</div>
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>

      {/* Overlay to close detail panel */}
      {showDetailPanel && (
        <div className="detail-overlay" onClick={() => setShowDetailPanel(false)} />
      )}

    </div>
  );
}

export default App;

import { useState, useEffect } from "react";
import "./App.css";
import YearlyBookChart from "./YearlyBookChart";
import PublicationVsReadChart from "./PublicationVsReadChart";
import BookLengthChart from "./BookLengthChart";
import BookGraph from "./components/BookGraph";

function App() {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);

  const [showTutorial, setShowTutorial] = useState(false); // Zichtbaarheid van de Goodreads-exportuitleg
  const [activeView, setActiveView] = useState("stats");   // Actief tabblad: "stats" of "suggestions"
  const [timeView, setTimeView] = useState("overall");     // Tijdsbereik: "overall" of "this_year"
  const [selectedBook, setSelectedBook] = useState(null);  // Huidig geselecteerd boek voor de graaf
  const [isUploading, setIsUploading] = useState(false);   // Of de CSV momenteel wordt verwerkt (voor laadbalk)

  // Paginastatistieken voor het huidige tijdsbereik
  const bookLengths = stats?.book_lengths?.[timeView];

  const getOldestPublicationYear = () => {
    return stats?.oldest_pub_year;
  };

  // Beschrijvende tekst onder het leesritme-diagram, afhankelijk van het tijdsbereik
  const getReadingOverTimeText = () => {
    const s = stats[timeView];
    if (!s) return "";
    return timeView === "overall"
      ? `Across your entire reading history, you've finished ${s.total_books} books.
 The chart above shows how your reading ebbs and flows over time.`
      : `So far this year, you've finished ${s.total_books} books.
 Your reading activity varies across the months.`;
  };

  // Beschrijvende tekst onder het publicatiejaar-diagram
  const getPublicationTimingText = () => {
    if (!stats) return "";

    const oldestYear = getOldestPublicationYear();

    return timeView === "overall"
      ? `Your reading spans a wide range of publication years,
       reaching back well beyond recent releases.
       ${oldestYear ? `The oldest book you’ve read was published in ${oldestYear}.` : ""}`
      : `This year’s reading includes books from different publication periods.
       ${oldestYear ? `The oldest one dates back to ${oldestYear}.` : ""}`;
  };

  // Verwerkt het gekozen CSV-bestand en stuurt het naar de backend
  const handleUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);
    setIsUploading(true);

    try {
      const res = await fetch("http://127.0.0.1:8000/api/upload_goodreads/", {
        method: "POST",
        body: formData
      });

      if (!res.ok) {
        throw new Error(`Server error: ${res.status}`);
      }

      const data = await res.json();

      setStats(data);
      setSelectedBook(data.books[0]); // Selecteer het eerste boek standaard voor de graaf
      setActiveView("stats");
      setError(null);
      console.log("First book:", data.books[0]);

    } catch (err) {
    setError(err.message);
    setStats(null);
  } finally {
    setIsUploading(false);
  }
};

// Polt elke 3 seconden de /covers/ endpoint om omslagen bij te werken
// die door het achtergrondproces zijn ingeladen na het uploaden
useEffect(() => {
  if (!stats) return;

  const interval = setInterval(async () => {
    const res = await fetch("http://127.0.0.1:8000/api/covers/");
    const data = await res.json();

    if (data.covers.length === 0) return;

    // Werk individuele boeken bij zonder de hele stats-state te vervangen
    setStats(prev => {
      const updated = { ...prev };
      updated.books = updated.books.map(book => {
        const found = data.covers.find(c => c.id === book.id);
        return found ? { ...book, cover_url: found.cover_url } : book;
      });
      return updated;
    });
  }, 3000);

  return () => clearInterval(interval); // Opruimen bij unmount of nieuwe stats
}, [stats]);

// Zet de applicatie terug naar de begintoestand
const handleReset = () => {
  setStats(null);
  setSelectedBook(null);
  setError(null);
  setTimeView("overall");
  setActiveView("stats");
};


  // Render
  return (
    <div style={{ padding: "2rem", fontFamily: "Arial" }}>
      <h1>BookTomo</h1>
    {isUploading && (
      <div className="loading-overlay">
        <div className="loading-card neu-card">
          <p>Crunching your books…</p>
          <div className="loading-bar">
          <div className="loading-bar-fill"/>
          </div>

          <p style={{ fontSize: "0.9rem", opacity: 0.7, marginTop: "o.5rem"}}>
            This can take a moment for large libraries
          </p>
        </div>
      </div>
    )}

      {!stats ? (
        <>
          <p>Upload your Goodreads CSV to see your reading stats!</p>
          <div className="upload-row">
            <label className="upload-button neu-card">
              Upload CSV
              <input type="file" onChange={handleUpload} style={{ display: "none" }} />
            </label>

            <button
              className="help-btn neu-card"
              onClick={() => setShowTutorial(!showTutorial)}
              aria-label="How to export from Goodreads">
              ?
            </button>
          </div>

          <div className={`tutorial-panel ${showTutorial ? "open" : ""}`}>
            <h3>How to export from Goodreads</h3>
            <ol>
              <li>Log in to Goodreads</li>
              <li>
                Click <strong>My Books</strong>
              </li>
              <li>
                Scroll down and click <strong>Import and Export</strong> under tools
              </li>
              <li>
                Click <strong>Export Library</strong>
              </li>
              <li>Download the CSV and upload it here</li>
            </ol>
          </div>
        </>
      ) : (
        <>
          <button className="upload-button neu-card" onClick={handleReset}>
            Upload New CSV
          </button>
        </>
      )}

  {stats && (
<div className="top-tabs">
  <button
    className={`upload-button neu-card ${activeView === "stats" ? "neu-pressed" : ""}`}
    onClick={() => setActiveView("stats")}
  >
    Stats
  </button>

  <button
    className={`upload-button neu-card ${activeView === "suggestions" ? "neu-pressed" : ""}`}
    onClick={() => setActiveView("suggestions")}
  >
    Suggestions
  </button>
</div>
)}

{activeView === "stats" && (
  <>
      {error && <p style={{ color: "red" }}>Error: {error}</p>}

      {stats && (
      <div className="stats-container">
        <div className="stats-box neu-card">
            <div className="stats-box-header" style={{ gridRow: "span 2" }}>
                <div className="view-toggle">
                  <button
                  className={`upload-button small neu-card ${timeView === "overall" ? "neu-pressed" : ""}`}
                  onClick={() => setTimeView("overall")}>
                    Overall
                  </button>

                  <button
                    className={`upload-button small neu-card ${timeView === "this_year" ? "neu-pressed" : ""}`}
                    onClick={() => setTimeView("this_year")}>
                    This Year
                  </button>
                </div>
            </div>
            <h2>{timeView === "overall" ? "All-time stats" : "This Year’s stats"}</h2>
            <p>Total books: {stats[timeView].total_books}</p>
            <p>Total pages: {stats[timeView].total_pages}</p>
            <p>Average rating: {stats[timeView].avg_rating}</p>
            <p>Top author: {stats[timeView].top_author || "N/A"}</p>

            <hr />

            <h3>Reading cadence</h3>
            <p>Avg days per book: {stats[timeView].cadence.avg_days}</p>
            <p>Median days per book: {stats[timeView].cadence.median_days}</p>
            <p>Fastest gap: {stats[timeView].cadence.fastest_days} days</p>
            <p>Longest gap: {stats[timeView].cadence.slowest_days} days</p>
          </div>

          <div className="chart-box neu-card">
            {timeView === "overall" && <YearlyBookChart yearlyData={stats.yearly_books} type="year" />}
            {timeView === "this_year" && <YearlyBookChart yearlyData={stats.monthly_books} type="month" />}
          </div>

          <div className="chart-box neu-card">
            {timeView === "overall" && <PublicationVsReadChart data={stats.scatter_publication_vs_read_all} type="year" />}
            {timeView === "this_year" && (
              <PublicationVsReadChart data={stats.scatter_publication_vs_read_year} type="month" />
            )}
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
              <div className="chart-box neu-card" style={{ gridColumn: "1 / 2" }}>
                {bookLengths?.histogram && <BookLengthChart data={bookLengths.histogram} />}
              </div>

              <div className="info-box2 neu-card" style={{ gridColumn: "1 / 2" }}>
                {bookLengths && (
                  <>
                    <p>
                      On average, your books are about <strong>{bookLengths?.average_pages}</strong> pages long.
                    </p>

                    {bookLengths?.longest_book &&
                      (() => {
                        const { title, author, pages } = bookLengths.longest_book;
                        return (
                          <p>
                            Your longest finished book was <strong>{title}</strong> by {author}, at {pages} pages.
                          </p>
                        );
                      })()}
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
  </>
)}

{activeView === "suggestions" && stats && (
  <div className="suggestions-layout">

    <div className="book-list neu-card">
      <h3>Your books</h3>

      <div className="book-list-scroll">
        {stats.books.map((book) => (
          <button
  key={book.id}
  className={`book-item ${selectedBook?.id === book.id ? "active" : ""}`}
  onClick={() => setSelectedBook(book)}
>
  <img
    src={book.cover_url || "/placeholder-book.png"}
    alt={book.title}
    className="book-cover"
    loading="lazy"
  />

  <div className="book-meta">
    <strong>{book.title}</strong>
    <div className="book-author">{book.author}</div>
  </div>
</button>

        ))}
      </div>
    </div>


    <div className="graph-container neu-card">
    <div className="graph-legend neu-card">
      <div className="legend-item">
        <span className="legend-dot read"></span>
        <span>Read book</span>
      </div>

      <div className="legend-item">
        <span className="legend-dot unread"></span>
        <span>Unread recommendation</span>
      </div>

      <div className="legend-item">
        <span className="legend-dot author"></span>
        <span>Author</span>
      </div>
    </div>
      {selectedBook ? (
        /* Laad de graaf als iframe: de backend genereert de pyvis-HTML per boek */
        <iframe
          src={`http://localhost:8000/api/graph/${encodeURIComponent("book::" + selectedBook.id)}`}
          width="100%"
          height="85%"
          style={{ border: "none", borderRadius: "16px" }}
          title="Book Graph"
        />
      ) : (
        <p>Select a book to see recommendations</p>
      )}
    </div>

  </div>
)}


    </div>
  );
}

export default App;

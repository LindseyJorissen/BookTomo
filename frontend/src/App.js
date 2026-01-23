import { useState } from "react";
import "./App.css";
import YearlyBookChart from "./YearlyBookChart";
import PublicationVsReadChart from "./PublicationVsReadChart";
import BookLengthChart from "./BookLengthChart";
import BookGraph from "./components/BookGraph";

function App() {
  // 1. state
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);
  const [showTutorial, setShowTutorial] = useState(false);

  const [activeView, setActiveView] = useState("stats"); // Stats | Suggestions
  const [timeView, setTimeView] = useState("overall");  // Overall | This Year
  const [selectedBook, setSelectedBook] = useState(null);


  // 2. helper functions
  const bookLengths = stats?.book_lengths?.[timeView];

  const getOldestPublicationYear = () => {
    return stats?.oldest_pub_year;
  };

  const getReadingOverTimeText = () => {
    const s = stats[timeView];
    if (!s) return "";
    return timeView === "overall"
      ? `Across your entire reading history, you've finished ${s.total_books} books.
 The chart above shows how your reading ebbs and flows over time.`
      : `So far this year, you've finished ${s.total_books} books.
 Your reading activity varies across the months.`;
  };

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

  // 3. handlers
  const handleUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

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
      setSelectedBook(data.books[0]);
      setActiveView("stats");
      setError(null);

    } catch (err) {
      setError(err.message);
      setStats(null);
    }
  };

const handleReset = () => {
  setStats(null);
  setSelectedBook(null);
  setError(null);
  setTimeView("overall");
  setActiveView("stats");
};


  // 4. render
  return (
    <div style={{ padding: "2rem", fontFamily: "Arial" }}>
      <h1>BookTomo</h1>

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
          {/* Row 1–2: stats (left) */}
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

          {/* Row 1: charts */}
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

          {/* Row 2: text */}
          <div className="info-box neu-card">
            <h3>Reading over time</h3>
            <p>{getReadingOverTimeText()}</p>
          </div>

          <div className="info-box neu-card">
            <h3>When you read books</h3>
            <p>{getPublicationTimingText()}</p>
          </div>

          {/* Row 3: book length chart */}
          <div className="right-grid">
            <div className="chart-stack">
              <div className="chart-box neu-card" style={{ gridColumn: "1 / 2" }}>
                {bookLengths?.histogram && <BookLengthChart data={bookLengths.histogram} />}
              </div>

              <div className="info-box2 neu-card" style={{ gridColumn: "1 / 2" }}>
                {bookLengths && (
                  <>
                    <p>
                      On average, your books are about <strong>{stats.book_lengths.average_pages}</strong> pages long.
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

    {/* LEFT: book selector */}
    <div className="book-list neu-card">
      <h3>Your books</h3>

      <div className="book-list-scroll">
        {stats.books.map((book) => (
          <button
            key={book.id}
            className="book-item"
            onClick={() => setSelectedBook(book)}
          >
            <strong>{book.title}</strong>
            <div className="book-author">{book.author}</div>
          </button>
        ))}
      </div>
    </div>

    {/* RIGHT: graph */}
    <div className="graph-container neu-card">
      {selectedBook ? (
        <iframe
          src={`http://localhost:8000/api/graph/${encodeURIComponent(`book::${selectedBook.id}`)}`}
          width="100%"
          height="100%"
          minHeight= "650px"
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

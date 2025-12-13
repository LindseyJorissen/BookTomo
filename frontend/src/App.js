import { useState } from "react";
import "./App.css";
import YearlyBookChart from "./YearlyBookChart";
import PublicationVsReadChart from "./PublicationVsReadChart";

function App() {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);
  const [view, setView] = useState("overall");
  const [showTutorial, setShowTutorial] = useState(false);

const getReadingOverTimeText = () => {
const s = stats[view];
if (!s) return "";

return view === "overall"
 ? `Across your entire reading history, you've finished ${s.total_books} books.
 The chart above shows how your reading ebbs and flows over time.`
 : `So far this year, you've finished ${s.total_books} books.
 Your reading activity varies across the months.`;
};

const getPublicationTimingText = () => {
const s = stats[view];
if (!s) return "";
    return view === "overall"
      ? `Your reading spans a wide range of publication years.
         ${s.top_author ? `One author you return to often is ${s.top_author}.` : ""}`
      : `This year’s reading includes books from different publication periods.
         ${s.top_author ? `${s.top_author} appears most frequently.` : ""}`;
  };

  const handleUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch("http://127.0.0.1:8000/api/upload_goodreads/", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        throw new Error(`Server error: ${res.status}`);
      }

      const data = await res.json();
      setStats(data);
      setError(null);
    } catch (err) {
      setError(err.message);
      setStats(null);
    }
  };

  const handleReset = () => {
    setStats(null);
    setError(null);
    setView("overall");
  };

  return (
    <div style={{ padding: "2rem", fontFamily: "Arial" }}>
      <h1>BookTomo</h1>

      {!stats ? (
        <>
          <p>Upload your Goodreads CSV to see your reading stats!</p>
          <div className="upload-row">
            <label className="upload-button">
                Upload CSV
            <input
              type="file"
              onChange={handleUpload}
              style={{ display: "none" }}
            />
          </label>

          <button className="help=btn" onClick={() => setShowTutorial(!showTutorial)} aria-label="How to export from Goodreads">
            ?
          </button>
        </div>

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
        </>
      ) : (
        <>
          <button className="reset-button" onClick={handleReset}>
            Upload New CSV
          </button>
        </>
      )}

      {error && <p style={{ color: "red" }}>Error: {error}</p>}

      {stats && (
        <div className="stats-container">

        {/* left column */}
          <div className="stats-box">
            <div style={{ marginBottom: "1rem" }}>
              <button
                className="small-button"
                onClick={() => setView("overall")}
                style={{
                  fontWeight: view === "overall" ? "bold" : "normal",
                  marginRight: "1rem",
                }}
              >
                Overall
              </button>
              <button
                className="small-button"
                onClick={() => setView("this_year")}
                style={{
                  fontWeight: view === "this_year" ? "bold" : "normal",
                }}
              >
                This Year
              </button>
            </div>

            <h2>
              {view === "overall" ? "All-time stats" : "This Year’s stats"}
            </h2>
            <p>Total books: {stats[view].total_books}</p>
            <p>Total pages: {stats[view].total_pages}</p>
            <p>Average rating: {stats[view].avg_rating}</p>
            <p>Top author: {stats[view].top_author || "N/A"}</p>
            <hr />

            <h3>Reading cadence</h3>
            <p>Avg days per book: {stats[view].cadence.avg_days}</p>
            <p>Median days per book: {stats[view].cadence.median_days}</p>
            <p>Fastest gap: {stats[view].cadence.fastest_days} days</p>
            <p>Longest gap: {stats[view].cadence.slowest_days} days</p>

          </div>

<div className="right-grid">
{/* charts right column*/}

{/* yearly books chart */}
<div className="chart-box">
  {view === "overall" && stats.yearly_books && (
    <YearlyBookChart yearlyData={stats.yearly_books} type="year" />
  )}
  {view === "this_year" && stats.monthly_books && (
    <YearlyBookChart yearlyData={stats.monthly_books} type="month" />
  )}
</div>

{/* publication vs read chart */}
<div className="chart-box">
  {view === "overall" &&
    stats.scatter_publication_vs_read_all?.length > 0 && (
      <PublicationVsReadChart
        data={stats.scatter_publication_vs_read_all}
        type="year"
      />
    )}

  {view === "this_year" &&
    stats.scatter_publication_vs_read_year?.length > 0 && (
      <PublicationVsReadChart
        data={stats.scatter_publication_vs_read_year}
        type="month"
      />
    )}
</div>

{/* text cards */}
<div className="info-box">
    <h3>Reading over time</h3>
    <p>{getReadingOverTimeText()}</p>
</div>
<div className="info-box">
    <h3>When you read books</h3>
    <p>{getPublicationTimingText()}</p>
    </div>

    </div>
</div>
)}


    </div>
  );
}

export default App;





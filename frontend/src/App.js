import { useState } from "react";
import "./App.css";
import YearlyBookChart from "./YearlyBookChart";

function App() {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);
  const [view, setView] = useState("overall"); // "overall" or "this_year"

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
          <label className="upload-button">
            Upload CSV
            <input
              type="file"
              onChange={handleUpload}
              style={{ display: "none" }}
            />
          </label>
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
          </div>

          <div className="chart-box">
            {view === "overall" && stats.yearly_books && (
              <YearlyBookChart yearlyData={stats.yearly_books} type="year" />
            )}

            {view === "this_year" && stats.monthly_books && (
              <YearlyBookChart yearlyData={stats.monthly_books} type="month" />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default App;

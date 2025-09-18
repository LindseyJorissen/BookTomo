import { useState } from "react";

function App() {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);

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

  return (
    <div style={{ padding: "2rem", fontFamily: "Arial" }}>
      <h1>📚 BookTomo</h1>
      <p>Upload your Goodreads CSV to see your reading stats!</p>
      <input type="file" onChange={handleUpload} />

      {error && <p style={{ color: "red" }}>Error: {error}</p>}

      {stats && (
        <div style={{ marginTop: "1rem" }}>
          <h2>Your Stats</h2>
          <p>Total books: {stats.total_books}</p>
          <p>Total pages: {stats.total_pages}</p>
          <p>Average rating: {stats.avg_rating}</p>
          <p>Top author: {stats.top_author}</p>
        </div>
      )}
    </div>
  );
}

export default App;

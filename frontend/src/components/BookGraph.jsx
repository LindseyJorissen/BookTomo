import React from "react";

export default function BookGraph({ bookId }) {
  if (!bookId) return null;

  const encodedBookId = encodeURIComponent(bookId);

  return (
    <div style={{ width: "100%", height: "650px" }}>
      <iframe
        src={`/api/graph/${encodedBookId}/`}
        width="100%"
        height="100%"
        style={{
          border: "none",
          borderRadius: "12px",
          background: "#fafafa",
        }}
        title="Book recommendation graph"
      />
    </div>
  );
}

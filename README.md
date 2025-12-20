# BookTomo

**BookTomo** is a year-in-review app for readers — think *Spotify Wrapped*, but for books.

It transforms your reading data into clear insights, visual summaries, and (experimentally) personalized recommendations. The goal of BookTomo is not only to show *what* you read, but also to help you understand patterns in your reading habits and discover new books you might enjoy.

---

## What BookTomo Does

BookTomo takes your **Goodreads CSV export** and turns it into:

- Yearly reading statistics (books read, pages, genres, ratings)
- Insights into your reading behavior
- Clean, visual charts and animations you can explore and share

---

## Core Features

- Upload your Goodreads CSV file  
- View yearly and overall reading statistics  
- Genre, rating, and author breakdowns  
- Interactive and animated visualizations  

---

## BookTomo Graph Engine (Experimental)

The **BookTomo Graph Engine** is an experimental recommendation and visualization system that extends BookTomo beyond statistics.

Instead of relying on simple filters, the Graph Engine models **books, authors, and genres as a network** and applies graph analysis techniques to explore how books relate to each other.

This makes it possible to generate **explainable recommendations** and visual reading networks.

Although Booktomo focuses on yearly reading summaries, recommendations are generated on a per-book basis. This avoids noise introduced by disliked or low-rated books and allows recommendations to be based on explicit user preference, resulting in more focused and explainable outcomes.

### What the Graph Engine Adds

- Models books, authors, and genres


import pandas as pd
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import datetime
from statistics import mean, median


def compute_cadence(date_series):
    dates = (
        date_series
        .dropna()
        .dt.date
        .drop_duplicates()
        .sort_values()
        .tolist()
    )

    if len(dates) < 2:
        return None

    gaps = [
        (dates[i] - dates[i - 1]).days
        for i in range(1, len(dates))
    ]

    return {
        "avg_days": round(mean(gaps), 1),
        "median_days": round(median(gaps), 1),
        "fastest_days": min(gaps),
        "slowest_days": max(gaps),
        "first_finished": dates[0].isoformat(),
        "last_finished": dates[-1].isoformat(),
    }


@csrf_exempt
def upload_goodreads(request):
    if request.method == "POST":
        try:
            file = request.FILES.get("file")
            if not file:
                return JsonResponse({"error": "No file uploaded"}, status=400)

            df = pd.read_csv(file)
            if "Exclusive Shelf" in df.columns:
                df = df[df["Exclusive Shelf"] == "read"]

            if "Date Read" not in df.columns:
                return JsonResponse({"error": "CSV missing 'Date Read' column"}, status=400)

            df["Date Read"] = pd.to_datetime(df["Date Read"], errors="coerce")
            df["Year Read"] = df["Date Read"].dt.year
            df["Month Read"] = df["Date Read"].dt.month

            current_year = datetime.date.today().year
            df_current_year = df[df["Year Read"] == current_year]
            cadence_overall = compute_cadence(df["Date Read"])
            cadence_this_year = compute_cadence(df_current_year["Date Read"])

            if "Number of Pages" in df.columns:
                pages = df["Number of Pages"].dropna()

                avg_pages = int(pages.mean()) if not pages.empty else 0
                max_pages = int(pages.max()) if not pages.empty else 0
                min_pages = int(pages.min()) if not pages.empty else 0

                longest_book = None
                if max_pages > 0:
                    longest_row = df.loc[df["Number of Pages"].idxmax()]
                    longest_book = {
                        "title": longest_row.get("Title"),
                        "author": longest_row.get("Author"),
                        "pages": int(longest_row.get("Number of Pages")),
                    }
            else:
                avg_pages = 0
                longest_book = None

            oldest_pub_year = None
            if "Original Publication Year" in df.columns:
                years = pd.to_numeric(df["Original Publication Year"], errors="coerce").dropna()
                if not years.empty:
                    oldest_pub_year = int(years.min())

            def compute_stats(subset):
                if subset.empty:
                    return {"total_books": 0, "total_pages": 0, "avg_rating": 0, "top_author": None}

                avg_rating = 0
                if "My Rating" in subset.columns:
                    rated_books = subset[subset["My Rating"] > 0]
                    if not rated_books.empty:
                        avg_rating = round(rated_books["My Rating"].mean(), 2)

                total_pages = int(
                    subset["Number of Pages"].fillna(0).sum()) if "Number of Pages" in subset.columns else 0
                top_author = subset["Author"].mode()[0] if "Author" in subset.columns and not subset.empty else None

                return {
                    "total_books": len(subset),
                    "total_pages": total_pages,
                    "avg_rating": avg_rating,
                    "top_author": top_author,
                }

            yearly_counts = df["Year Read"].dropna().value_counts().sort_index().to_dict()
            yearly_counts = {int(float(k)): v for k, v in yearly_counts.items()}

            monthly_counts = (
                df_current_year["Month Read"].dropna().value_counts().sort_index().to_dict()
                if not df_current_year.empty
                else {}
            )

            if "Original Publication Year" in df.columns:
                df["Original Publication Year"] = pd.to_numeric(df["Original Publication Year"], errors="coerce")

                pub_counts_all = (
                    df["Original Publication Year"].dropna().astype(int).value_counts().sort_index().to_dict()
                )

                pub_counts_this_year = (
                    df_current_year["Original Publication Year"]
                    .dropna()
                    .astype(int)
                    .value_counts()
                    .sort_index()
                    .to_dict()
                    if not df_current_year.empty
                    else {}
                )
            else:
                pub_counts_all, pub_counts_this_year = {}, {}

            scatter_all = (
                df[["Original Publication Year", "Year Read"]]
                .dropna()
                .assign(
                    Original_Publication_Year=lambda d: pd.to_numeric(
                        d["Original Publication Year"], errors="coerce"
                    ),
                    Year_Read=lambda d: pd.to_numeric(d["Year Read"], errors="coerce"),
                )
                .dropna(subset=["Original_Publication_Year", "Year_Read"])
            )
            scatter_points_all = [
                {"pub_year": int(row["Original Publication Year"]), "read_value": int(row["Year Read"])}
                for _, row in scatter_all.iterrows()
            ]

            scatter_year = (
                df_current_year[["Original Publication Year", "Month Read"]]
                .dropna()
                .assign(
                    Original_Publication_Year=lambda d: pd.to_numeric(
                        d["Original Publication Year"], errors="coerce"
                    ),
                    Month_Read=lambda d: pd.to_numeric(d["Month Read"], errors="coerce"),
                )
                .dropna(subset=["Original_Publication_Year", "Month_Read"])
                if not df_current_year.empty
                else pd.DataFrame(columns=["Original Publication Year", "Month Read"])
            )
            scatter_points_this_year = [
                {"pub_year": int(row["Original Publication Year"]), "read_value": int(row["Month Read"])}
                for _, row in scatter_year.iterrows()
            ]

            stats = {
                "overall": {
                    **compute_stats(df),
                    "cadence": cadence_overall,
                },
                "this_year": {
                    **compute_stats(df_current_year),
                    "cadence": cadence_this_year,
                },
                "yearly_books": yearly_counts,
                "monthly_books": monthly_counts,
                "publication_years_overall": pub_counts_all,
                "publication_years_this_year": pub_counts_this_year,
                "scatter_publication_vs_read_all": scatter_points_all,
                "scatter_publication_vs_read_year": scatter_points_this_year,

                "book_lenghts": {
                    "average_pages": avg_pages,
                    "longest_book": longest_book,
                },
                "oldest_pub_year": oldest_pub_year,
            }

            return JsonResponse(stats)

        except Exception as e:
            # return JsonResponse({"error": str(e)}, status=500)
            raise

    return JsonResponse({"error": "POST request required"}, status=400)

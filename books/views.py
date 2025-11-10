import pandas as pd
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import datetime

@csrf_exempt
def upload_goodreads(request):
    if request.method == "POST":
        try:
            file = request.FILES.get("file")
            if not file:
                return JsonResponse({"error": "No file uploaded"}, status=400)

            df = pd.read_csv(file)

            if "Date Read" not in df.columns:
                return JsonResponse({"error": "CSV missing 'Date Read' column"}, status=400)

            df["Date Read"] = pd.to_datetime(df["Date Read"], errors="coerce")
            df["Year Read"] = df["Date Read"].dt.year
            df["Month Read"] = df["Date Read"].dt.month

            current_year = datetime.date.today().year
            df_current_year = df[df["Year Read"] == current_year]

            def compute_stats(subset):
                if subset.empty:
                    return {"total_books": 0, "total_pages": 0, "avg_rating": 0, "top_author": None}

                avg_rating = 0
                if "My Rating" in subset.columns:
                    rated_books = subset[subset["My Rating"] > 0]
                    if not rated_books.empty:
                        avg_rating = round(rated_books["My Rating"].mean(), 2)

                total_pages = int(subset["Number of Pages"].fillna(0).sum()) if "Number of Pages" in subset.columns else 0
                top_author = subset["Author"].mode()[0] if "Author" in subset.columns and not subset.empty else None

                return {
                    "total_books": len(subset),
                    "total_pages": total_pages,
                    "avg_rating": avg_rating,
                    "top_author": top_author,
                }

            yearly_counts = (
                df["Year Read"]
                .dropna()
                .value_counts()
                .sort_index()
                .to_dict()
            )

            monthly_counts = (
                df_current_year["Month Read"]
                .dropna()
                .value_counts()
                .sort_index()
                .to_dict()
                if not df_current_year.empty
                else {}
            )

            stats = {
                "overall": compute_stats(df),
                "this_year": compute_stats(df_current_year),
                "yearly_books": yearly_counts,
                "monthly_books": monthly_counts,
            }

            return JsonResponse(stats)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "POST request required"}, status=400)

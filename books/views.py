import pandas as pd
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import datetime

@csrf_exempt
def upload_goodreads(request):
    if request.method == "POST":
        file = request.FILES.get("file")
        if not file:
            return JsonResponse({"error": "No file uploaded"}, status=400)

        df = pd.read_csv(file)

        if "Date Read" not in df.columns:
            return JsonResponse({"error": "CSV missing 'Date Read' column"}, status=400)

        df["Year Read"] = pd.to_datetime(df["Date Read"], errors="coerce").dt.year
        current_year = datetime.date.today().year
        df_current_year = df[df["Year Read"] == current_year]

        def compute_stats(subset):
            if "My Rating" in subset.columns:
                rated_books = subset[subset["My Rating"] > 0]
                avg_rating = round(rated_books["My Rating"].mean(), 2) if not rated_books.empty else 0
            else:
                avg_rating = 0

            return {
                "total_books": len(subset),
                "total_pages": int(
                    subset["Number of Pages"].fillna(0).sum()
                ) if "Number of Pages" in subset.columns else 0,
                "avg_rating": avg_rating,
                "top_author": subset["Author"].mode()[0]
                if "Author" in subset.columns and not subset.empty
                else None,
            }

        yearly_counts = (
            df["Year Read"]
            .dropna()
            .value_counts()
            .sort_index()
            .to_dict()
        )

        stats = {
            "overall": compute_stats(df),
            "this_year": compute_stats(df_current_year),
            "yearly_books": yearly_counts,
        }

        return JsonResponse(stats)

    return JsonResponse({"error": "POST request required"}, status=400)

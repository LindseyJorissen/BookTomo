import pandas as pd
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
def upload_goodreads(request):
    if request.method == "POST":
        # Get the uploaded file
        file = request.FILES.get("file")
        if not file:
            return JsonResponse({"error": "No file uploaded"}, status=400)

        df = pd.read_csv(file)

        if "Date Read" not in df.columns:
            return JsonResponse({"error": "CSV missing 'Date Read' column"}, status=400)

        # Filtering by year
        df["Year Read"] = pd.to_datetime(df["Date Read"], errors="coerce").dt.year
        df_current_year = df[df["Year Read"] == 2025]

        if "My Rating" in df_current_year.columns:
            rated_books = df_current_year[df_current_year["My Rating"] > 0]
            avg_rating = round(rated_books["My Rating"].mean(), 2) if not rated_books.empty else 0
        else:
            avg_rating = 0
            
        stats = {
            "total_books": len(df_current_year),
            "total_pages": int(df_current_year["Number of Pages"].fillna(0).sum()) if "Number of Pages" in df_current_year.columns else 0,
            "avg_rating": avg_rating,
            "top_author": df_current_year["Author"].mode()[0] if "Author" in df_current_year.columns and not df_current_year.empty else None,
        }

        return JsonResponse(stats)

    # No POST request error
    return JsonResponse({"error": "POST request required"}, status=400)

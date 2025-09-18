import pandas as pd
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

# Disable CSRF for simplicity (okay for local/dev)
@csrf_exempt
def upload_goodreads(request):
    if request.method == "POST":
        # Get the uploaded file
        file = request.FILES.get("file")
        if not file:
            return JsonResponse({"error": "No file uploaded"}, status=400)

        # Read CSV into pandas DataFrame
        df = pd.read_csv(file)

        # Make sure the CSV has a Date Read column
        if "Date Read" not in df.columns:
            return JsonResponse({"error": "CSV missing 'Date Read' column"}, status=400)

        # Filter by year (example: 2025)
        df["Year Read"] = pd.to_datetime(df["Date Read"], errors="coerce").dt.year
        df_current_year = df[df["Year Read"] == 2025]

        # Compute stats
        stats = {
            "total_books": len(df_current_year),
            "total_pages": int(df_current_year["Number of Pages"].fillna(0).sum()) if "Number of Pages" in df_current_year.columns else 0,
            "avg_rating": round(df_current_year["My Rating"].mean(), 2) if "My Rating" in df_current_year.columns else 0,
            "top_author": df_current_year["Author"].mode()[0] if "Author" in df_current_year.columns and not df_current_year.empty else None,
        }

        return JsonResponse(stats)

    # Not a POST request
    return JsonResponse({"error": "POST request required"}, status=400)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("books", "0002_bookgenres"),
    ]

    operations = [
        # Add Google Books genre fields to CachedBook
        migrations.AddField(
            model_name="cachedbook",
            name="google_books_genres",
            field=models.JSONField(default=list),
        ),
        migrations.AddField(
            model_name="cachedbook",
            name="google_books_fetched",
            field=models.BooleanField(default=False),
        ),
        # Remove the fetched_at timestamp — records are now permanent, no TTL
        migrations.RemoveField(
            model_name="cachedbook",
            name="fetched_at",
        ),
    ]

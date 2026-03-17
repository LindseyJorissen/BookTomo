from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("books", "0003_cachedbook_google_books"),
    ]

    operations = [
        migrations.AddField(
            model_name="cachedbook",
            name="is_read",
            field=models.BooleanField(default=False),
        ),
    ]

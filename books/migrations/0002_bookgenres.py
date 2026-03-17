from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("books", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="BookGenres",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("goodreads_id", models.CharField(max_length=50, unique=True)),
                ("title", models.CharField(blank=True, max_length=500)),
                ("author", models.CharField(blank=True, max_length=300)),
                ("genres", models.JSONField(default=list)),
            ],
            options={
                "indexes": [models.Index(fields=["goodreads_id"], name="books_bookgenres_gr_id_idx")],
            },
        ),
    ]

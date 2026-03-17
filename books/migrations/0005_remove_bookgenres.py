from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("books", "0004_cachedbook_is_read"),
    ]

    operations = [
        migrations.DeleteModel(name="BookGenres"),
    ]

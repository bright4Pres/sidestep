from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("brt", "0005_alter_productsize_price"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="is_published",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="product",
            name="published_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

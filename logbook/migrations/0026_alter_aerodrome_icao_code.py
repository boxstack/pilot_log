# Generated by Django 4.2.7 on 2023-11-04 16:30

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("logbook", "0025_pilot_only_one_me"),
    ]

    operations = [
        migrations.AlterField(
            model_name="aerodrome",
            name="icao_code",
            field=models.CharField(max_length=4, unique=True),
        ),
    ]

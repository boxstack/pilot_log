# Generated by Django 4.2.5 on 2023-09-10 16:21

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("logbook", "0011_alter_aircraft_options"),
    ]

    operations = [
        migrations.AddField(
            model_name="aircraft",
            name="currency_required",
            field=models.BooleanField(default=False),
        ),
    ]

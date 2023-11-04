from datetime import UTC, datetime
from typing import Optional

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import CheckConstraint, F, Q, UniqueConstraint
from django_countries.fields import CountryField

from .statistics.currency import NinetyDaysCurrency, get_ninety_days_currency


class AircraftType(models.TextChoices):
    GLD = "GLD", "Glider"
    TMG = "TMG", "Touring Motor Glider"
    SEP = "SEP", "Single Engine Piston"


class FunctionType(models.TextChoices):
    PIC = "PIC", "Pilot-in-Command"
    DUAL = "DUAL", "Dual instruction time"


class LaunchType(models.TextChoices):
    SELF = "SELF", "Self-launch"
    WINCH = "WINCH", "Winch launch"
    TOW = "TOW", "Aerotow"


class SpeedUnit(models.TextChoices):
    KMH = "KMH", "km/h"
    KT = "KT", "kt"
    MPH = "MPH", "mph"


class Aerodrome(models.Model):
    name = models.CharField(max_length=75)
    city = models.CharField(max_length=75)
    country = CountryField()
    icao_code = models.CharField(max_length=4)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    elevation = models.IntegerField()
    priority = models.IntegerField()

    class Meta:
        ordering = ("priority",)

    def __str__(self):
        return f"{self.icao_code} ({self.name})"


class Aircraft(models.Model):
    type = models.CharField(max_length=3, choices=AircraftType.choices)
    maker = models.CharField(max_length=64)
    model = models.CharField(max_length=64)

    # https://www.icao.int/publications/doc8643/pages/search.aspx
    icao_designator = models.CharField(max_length=4)

    registration = models.CharField(max_length=9, unique=True)

    currency_required = models.BooleanField(default=False)

    speed_unit = models.CharField(max_length=3, choices=SpeedUnit.choices)

    v_r = models.PositiveSmallIntegerField(verbose_name="Vr", help_text="Rotation speed", blank=True, null=True)
    v_y = models.PositiveSmallIntegerField(
        verbose_name="Vy",
        help_text="Best rate of climb speed",
        blank=True,
        null=True,
    )
    v_bg = models.PositiveSmallIntegerField(verbose_name="Vbg", help_text="Best glide speed", blank=True, null=True)
    v_app = models.PositiveSmallIntegerField(verbose_name="Vapp", help_text="Approach speed", blank=True, null=True)
    v_ref = models.PositiveSmallIntegerField(
        verbose_name="Vref",
        help_text="Uncorrected final approach speed",
        blank=True,
        null=True,
    )
    v_s = models.PositiveSmallIntegerField(verbose_name="Vs", help_text="Stall speed", blank=True, null=True)
    v_c = models.PositiveSmallIntegerField(verbose_name="Vc", help_text="Cruise speed", blank=True, null=True)

    demonstrated_crosswind = models.PositiveSmallIntegerField(
        help_text="Demonstrated crosswind in KT",
        blank=True,
        null=True,
    )

    class Meta:
        ordering = ("registration",)
        verbose_name_plural = "aircraft"

    def __str__(self):
        return f"{self.registration} ({self.maker} {self.model})"

    @property
    def currency_status(self) -> Optional[NinetyDaysCurrency]:
        return get_ninety_days_currency(LogEntry.objects.filter(aircraft=self)) if self.currency_required else None


class Pilot(models.Model):
    first_name = models.CharField(max_length=30)
    last_name = models.CharField(max_length=150)

    self = models.BooleanField(default=False)

    class Meta:
        ordering = ("last_name",)
        unique_together = ("first_name", "last_name")

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class LogEntry(models.Model):
    aircraft = models.ForeignKey(Aircraft, on_delete=models.PROTECT)

    from_aerodrome = models.ForeignKey(Aerodrome, on_delete=models.PROTECT, related_name="from_aerodrome_set")
    to_aerodrome = models.ForeignKey(Aerodrome, on_delete=models.PROTECT, related_name="to_aerodrome_set")

    departure_time = models.DateTimeField(unique=True)
    arrival_time = models.DateTimeField(unique=True)

    landings = models.PositiveSmallIntegerField(default=1)

    time_function = models.CharField(max_length=5, choices=FunctionType.choices)

    pilot = models.ForeignKey(Pilot, on_delete=models.PROTECT, related_name="pilot_set")
    copilot = models.ForeignKey(Pilot, on_delete=models.PROTECT, related_name="copilot_set", blank=True, null=True)

    launch_type = models.CharField(max_length=5, blank=True, choices=LaunchType.choices)

    remarks = models.CharField(max_length=255, blank=True)

    cross_country = models.BooleanField(default=False)
    night = models.BooleanField(default=False)

    slots = models.PositiveSmallIntegerField(default=1, help_text="Number of logbook slots for this entry.")

    class Meta:
        constraints = (
            CheckConstraint(check=Q(arrival_time__gt=F("departure_time")), name="arrival_after_departure"),
            CheckConstraint(check=~Q(copilot=F("pilot")), name="copilot_not_pilot"),
            CheckConstraint(
                check=(
                    Q(time_function=FunctionType.PIC)  # PIC time may be XC or not XC
                    | ~Q(time_function=FunctionType.PIC) & Q(cross_country=False)  # non-PIC time must be non-XC
                ),
                name="no_pic_no_xc",
            ),
        )
        ordering = ("-arrival_time",)
        verbose_name_plural = "Log entries"

    def __str__(self):
        duration = (self.arrival_time - self.departure_time).total_seconds()
        duration_hours = int(duration // 3600)
        duration_minutes = int((duration - duration_hours * 3600) // 60)
        remarks = f"({self.launch_type})" if self.launch_type else ""
        return (
            f"{self.departure_time.strftime('%Y-%m-%d %H:%M')} - {self.arrival_time.strftime('%H:%M')} "
            f"({duration_hours:02}:{duration_minutes:02}) "
            f"{self.aircraft.registration} ({self.aircraft.type}) "
            f"{self.from_aerodrome.icao_code} -> {self.to_aerodrome.icao_code} "
            f"{self.pilot.last_name}{' / ' + self.copilot.last_name if self.copilot is not None else ''} "
            f"{'[XC] ' if self.cross_country else ''}"
            f"{'[N] ' if self.night else ''}"
            f"{remarks}".strip()
        )

    def clean(self):
        # Check constraints can't reference other tables; it's possible via UDFs, but not universally supported by RDBs
        if (
            self.aircraft_id is not None  # checks if foreign key is set to avoid `RelatedObjectDoesNotExist` exception!
            and self.aircraft.type == AircraftType.GLD
            and not self.launch_type
        ):
            raise ValidationError("Launch type is required for gliders!")


class Certificate(models.Model):
    name = models.CharField(max_length=255)
    number = models.CharField(max_length=255, blank=True)
    issue_date = models.DateField()
    valid_until = models.DateField(blank=True, null=True)
    authority = models.CharField(max_length=255)
    remarks = models.CharField(max_length=255, blank=True)
    supersedes = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="supersedes_set",
    )

    class Meta:
        constraints = (
            CheckConstraint(
                check=Q(valid_until__isnull=True) | Q(valid_until__gt=F("issue_date")),
                name="validity_after_issue",
            ),
            CheckConstraint(
                check=~Q(id=F("supersedes")),
                name="supersedes_self",
            ),
            UniqueConstraint(
                fields=["supersedes"],
                condition=Q(supersedes__isnull=False),
                name="supersedes_unique",
            ),
        )
        ordering = ("name", F("supersedes").desc(nulls_last=True), "-valid_until")

    def __str__(self):
        return f"{self.name}{' / {}'.format(self.number) if self.number else ''} ({self.issue_date})"

    @property
    def valid(self) -> bool:
        return (
            self.valid_until is None or self.valid_until >= datetime.now(tz=UTC).date()
        ) and not self.supersedes_set.count()

    @property
    def superseded_by(self) -> Optional["Certificate"]:
        return self.supersedes_set.first()

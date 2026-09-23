import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.fleets.models import Fleet
from apps.fleets.querysets import ArchivableQuerySet


class Radio(models.Model):
    """One physical radio, scoped to exactly one fleet."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SPARE = "spare", "Spare"
        REPAIR = "repair", "In repair"
        RETIRED = "retired", "Retired"

    class Purpose(models.TextChoices):
        SPOTTER = "spotter", "Spotter"
        CREW = "crew", "Crew"
        RACE_CONTROL = "race_control", "Race control"
        OTHER = "other", "Other"

    fleet = models.ForeignKey(Fleet, on_delete=models.CASCADE, related_name="radios")
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    asset_label = models.CharField(max_length=100)
    manufacturer = models.CharField(max_length=100, blank=True)
    model = models.CharField(max_length=100, blank=True)
    serial = models.CharField(max_length=100, blank=True)
    radio_id = models.CharField(max_length=100, blank=True)
    band = models.CharField(max_length=50, blank=True)
    firmware = models.CharField(max_length=50, blank=True)
    purpose = models.CharField(max_length=20, choices=Purpose.choices, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    notes = models.TextField(blank=True)

    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ArchivableQuerySet.as_manager()

    class Meta:
        ordering = ["asset_label"]
        constraints = [
            models.UniqueConstraint(
                fields=["fleet", "asset_label"], name="unique_radio_asset_label_per_fleet"
            ),
        ]
        indexes = [
            models.Index(fields=["fleet", "status"]),
            models.Index(fields=["fleet", "asset_label"]),
        ]

    def __str__(self):
        return self.asset_label

    @property
    def is_archived(self):
        return self.archived_at is not None

    def current_battery_assignment(self):
        return (
            self.battery_assignments.filter(ended_at__isnull=True).select_related("battery").first()
        )


class Battery(models.Model):
    """One tracked physical battery pack, scoped to exactly one fleet."""

    class Condition(models.TextChoices):
        GOOD = "good", "Good"
        FAIR = "fair", "Fair"
        REPLACE = "replace", "Needs replacement"

    fleet = models.ForeignKey(Fleet, on_delete=models.CASCADE, related_name="batteries")
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    asset_label = models.CharField(max_length=100)
    maker = models.CharField(max_length=100, blank=True)
    model = models.CharField(max_length=100, blank=True)
    serial = models.CharField(max_length=100, blank=True)
    chemistry = models.CharField(max_length=50, blank=True)
    capacity = models.CharField(max_length=50, blank=True, help_text="e.g. 2200 mAh")
    condition = models.CharField(max_length=20, choices=Condition.choices, default=Condition.GOOD)
    notes = models.TextField(blank=True)

    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ArchivableQuerySet.as_manager()

    class Meta:
        ordering = ["asset_label"]
        verbose_name_plural = "batteries"
        constraints = [
            models.UniqueConstraint(
                fields=["fleet", "asset_label"], name="unique_battery_asset_label_per_fleet"
            ),
        ]
        indexes = [
            models.Index(fields=["fleet", "condition"]),
            models.Index(fields=["fleet", "asset_label"]),
        ]

    def __str__(self):
        return self.asset_label

    @property
    def is_archived(self):
        return self.archived_at is not None

    def current_assignment(self):
        return self.assignments.filter(ended_at__isnull=True).select_related("radio").first()


class BatteryAssignment(models.Model):
    """A dated link between a battery and the radio it was issued to.

    At most one active (ended_at is null) assignment may exist per battery,
    and at most one per radio -- assigning a battery elsewhere, or assigning
    a new battery to a radio, ends the prior active assignment automatically
    (see `apps.radios.services.assign_battery`), so this table is always a
    consistent swap history rather than a single mutable "current battery"
    field.
    """

    fleet = models.ForeignKey(Fleet, on_delete=models.CASCADE, related_name="battery_assignments")
    battery = models.ForeignKey(Battery, on_delete=models.CASCADE, related_name="assignments")
    radio = models.ForeignKey(Radio, on_delete=models.CASCADE, related_name="battery_assignments")

    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="battery_assignments_made",
    )
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["battery"],
                condition=models.Q(ended_at__isnull=True),
                name="unique_active_assignment_per_battery",
            ),
            models.UniqueConstraint(
                fields=["radio"],
                condition=models.Q(ended_at__isnull=True),
                name="unique_active_assignment_per_radio",
            ),
        ]
        indexes = [
            models.Index(fields=["fleet"]),
        ]

    def __str__(self):
        return f"{self.battery} -> {self.radio} ({self.started_at:%Y-%m-%d})"

    @property
    def is_active(self):
        return self.ended_at is None


class MaintenanceEvent(models.Model):
    """A dated note about repair, inspection, firmware or another action."""

    class Kind(models.TextChoices):
        REPAIR = "repair", "Repair"
        INSPECTION = "inspection", "Inspection"
        FIRMWARE = "firmware", "Firmware update"
        ANTENNA = "antenna", "Antenna"
        OTHER = "other", "Other"

    fleet = models.ForeignKey(Fleet, on_delete=models.CASCADE, related_name="maintenance_events")
    radio = models.ForeignKey(Radio, on_delete=models.CASCADE, related_name="maintenance_events")
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.OTHER)
    occurred_at = models.DateField(default=timezone.localdate)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="maintenance_events_recorded",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_at", "-created_at"]
        indexes = [
            models.Index(fields=["fleet", "radio"]),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} on {self.radio} ({self.occurred_at})"

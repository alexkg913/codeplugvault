import uuid

from django.db import models

from apps.fleets.models import Fleet


class RadioQuerySet(models.QuerySet):
    def active(self):
        return self.filter(archived_at__isnull=True)

    def archived(self):
        return self.filter(archived_at__isnull=False)


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

    objects = RadioQuerySet.as_manager()

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

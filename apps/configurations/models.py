import uuid

from django.conf import settings
from django.db import models

from apps.fleets.models import Fleet
from apps.fleets.querysets import ArchivableQuerySet
from apps.radios.models import Radio


class Configuration(models.Model):
    """A named configuration family, e.g. "Race Weekend". Not itself a version."""

    fleet = models.ForeignKey(Fleet, on_delete=models.CASCADE, related_name="configurations")
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    compatibility_notes = models.TextField(
        blank=True, help_text="e.g. radio models/firmware this family is meant for"
    )

    archived_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="configurations_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ArchivableQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["fleet", "name"], name="unique_configuration_name_per_fleet"
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def is_archived(self):
        return self.archived_at is not None


class ConfigurationVersion(models.Model):
    """An immutable-once-published snapshot within a Configuration family."""

    class State(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

    fleet = models.ForeignKey(
        Fleet, on_delete=models.CASCADE, related_name="configuration_versions"
    )
    configuration = models.ForeignKey(
        Configuration, on_delete=models.CASCADE, related_name="versions"
    )
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    # Assigned sequentially per configuration (see services.create_version), not
    # user-entered, so it can't collide. `label` is an optional human nickname.
    version_number = models.PositiveIntegerField()
    label = models.CharField(max_length=150, blank=True)
    release_notes = models.TextField(blank=True)
    state = models.CharField(max_length=10, choices=State.choices, default=State.DRAFT)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="configuration_versions_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-version_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["configuration", "version_number"],
                name="unique_version_number_per_configuration",
            ),
        ]

    def __str__(self):
        return f"{self.configuration.name} v{self.version_number}"

    @property
    def is_draft(self):
        return self.state == self.State.DRAFT

    @property
    def is_published(self):
        return self.state == self.State.PUBLISHED

    @property
    def display_name(self):
        return f"v{self.version_number}" + (f" — {self.label}" if self.label else "")


class ChannelSnapshot(models.Model):
    """One manually-entered channel row within a version.

    `position` is the stable comparison key across versions of the same
    configuration family (see apps.configurations.comparison): it stands for
    the channel's memory slot, so it is meaningful content, not just display
    order. Moving what occupies a given position between versions is treated
    as a real change, not a cosmetic reorder -- see comparison.py.

    This is a manually entered description of a channel, never a claim that
    an attached vendor file was parsed.
    """

    class Mode(models.TextChoices):
        ANALOG = "analog", "Analog"
        DIGITAL = "digital", "Digital (DMR)"

    fleet = models.ForeignKey(Fleet, on_delete=models.CASCADE, related_name="channel_snapshots")
    version = models.ForeignKey(
        ConfigurationVersion, on_delete=models.CASCADE, related_name="channels"
    )

    position = models.PositiveIntegerField()
    zone = models.CharField(max_length=100, blank=True)
    name = models.CharField(max_length=100)
    mode = models.CharField(max_length=10, choices=Mode.choices)

    rx_frequency = models.DecimalField(max_digits=10, decimal_places=5, null=True, blank=True)
    tx_frequency = models.DecimalField(max_digits=10, decimal_places=5, null=True, blank=True)

    # Analog
    rx_tone = models.CharField(max_length=20, blank=True, help_text="CTCSS/DCS, if used")
    tx_tone = models.CharField(max_length=20, blank=True)

    # Digital (DMR)
    color_code = models.PositiveSmallIntegerField(null=True, blank=True)
    timeslot = models.PositiveSmallIntegerField(null=True, blank=True, choices=[(1, "1"), (2, "2")])

    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(
                fields=["version", "position"], name="unique_channel_position_per_version"
            ),
        ]

    def __str__(self):
        return f"#{self.position} {self.name}"

    #: Fields compared by apps.configurations.comparison.compare_versions.
    COMPARISON_FIELDS = (
        "zone",
        "name",
        "mode",
        "rx_frequency",
        "tx_frequency",
        "rx_tone",
        "tx_tone",
        "color_code",
        "timeslot",
        "notes",
    )


class VersionAttachment(models.Model):
    """A privately-stored vendor file (or supporting doc) attached to a version.

    `storage_key` is a random filename on disk (see apps.configurations.services);
    `original_filename` is what the uploader called it and is the only filename
    ever shown or sent back on download. There is never a public URL to this file.
    """

    fleet = models.ForeignKey(Fleet, on_delete=models.CASCADE, related_name="version_attachments")
    version = models.ForeignKey(
        ConfigurationVersion, on_delete=models.CASCADE, related_name="attachments"
    )

    storage_key = models.CharField(max_length=255, unique=True)
    original_filename = models.CharField(max_length=255)
    byte_size = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64)

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="version_attachments_uploaded",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.original_filename


class ProgrammingRecord(models.Model):
    """An observed event: this version was programmed into this radio.

    Selecting a version as a target is not proof it was programmed -- only
    creating this record is. The latest record for a radio is its displayed
    current configuration.
    """

    fleet = models.ForeignKey(Fleet, on_delete=models.CASCADE, related_name="programming_records")
    radio = models.ForeignKey(Radio, on_delete=models.CASCADE, related_name="programming_records")
    version = models.ForeignKey(
        ConfigurationVersion, on_delete=models.CASCADE, related_name="programming_records"
    )

    programmed_at = models.DateTimeField()
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="programming_records_recorded",
    )
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-programmed_at", "-created_at"]
        indexes = [
            models.Index(fields=["fleet", "radio"]),
        ]

    def __str__(self):
        return f"{self.version} -> {self.radio} ({self.programmed_at:%Y-%m-%d})"

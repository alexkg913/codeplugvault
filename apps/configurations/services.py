"""Configuration/version/attachment/programming rules centralized here rather
than scattered across views, per the project brief.
"""

import hashlib
import uuid

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models, transaction
from django.utils import timezone

from .models import Configuration, ConfigurationVersion, ProgrammingRecord, VersionAttachment


def get_attachment_storage():
    # Constructed fresh on every call (rather than a module-level singleton) so
    # it always reflects the current PRIVATE_MEDIA_ROOT -- in particular so
    # tests can redirect it to a temp directory via the `settings` fixture.
    return FileSystemStorage(location=str(settings.PRIVATE_MEDIA_ROOT), base_url=None)


class CrossFleetError(Exception):
    """Raised when linked records don't belong to the fleet being acted on."""


class VersionNotDraftError(Exception):
    """Raised when a mutation is attempted on a version that isn't a draft."""


class VersionNotPublishedError(Exception):
    """Raised when a programming record targets a version that isn't published."""


class AttachmentUploadError(Exception):
    """Raised for a rejected or failed upload; safe to show to the user."""


@transaction.atomic
def create_version(*, configuration, created_by, label="", release_notes=""):
    # Lock the parent row so two concurrent "new version" clicks can't compute
    # the same next number.
    configuration = Configuration.objects.select_for_update().get(pk=configuration.pk)
    next_number = (
        configuration.versions.aggregate(models.Max("version_number"))["version_number__max"] or 0
    ) + 1
    return ConfigurationVersion.objects.create(
        fleet=configuration.fleet,
        configuration=configuration,
        version_number=next_number,
        label=label,
        release_notes=release_notes,
        created_by=created_by,
    )


def publish_version(version):
    if not version.is_draft:
        raise VersionNotDraftError("Only a draft version can be published.")
    version.state = ConfigurationVersion.State.PUBLISHED
    version.published_at = timezone.now()
    version.save(update_fields=["state", "published_at"])
    return version


def store_attachment(*, fleet, version, uploaded_file, uploaded_by):
    if version.fleet_id != fleet.id:
        raise CrossFleetError("Version does not belong to this fleet.")

    ext = "." + uploaded_file.name.rsplit(".", 1)[-1].lower() if "." in uploaded_file.name else ""
    if ext not in settings.ATTACHMENT_ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(settings.ATTACHMENT_ALLOWED_EXTENSIONS))
        raise AttachmentUploadError(
            f"'{ext or 'unknown'}' files aren't allowed. Allowed: {allowed}"
        )

    if uploaded_file.size > settings.ATTACHMENT_MAX_BYTES:
        max_mb = settings.ATTACHMENT_MAX_BYTES // (1024 * 1024)
        raise AttachmentUploadError(f"File is too large (max {max_mb} MB).")

    digest = hashlib.sha256()
    for chunk in uploaded_file.chunks():
        digest.update(chunk)
    uploaded_file.seek(0)

    storage = get_attachment_storage()
    storage_key = f"{uuid.uuid4().hex}{ext}"
    try:
        storage.save(storage_key, uploaded_file)
    except OSError as exc:
        raise AttachmentUploadError("Couldn't save the file. Try again.") from exc

    try:
        return VersionAttachment.objects.create(
            fleet=fleet,
            version=version,
            storage_key=storage_key,
            original_filename=uploaded_file.name,
            byte_size=uploaded_file.size,
            sha256=digest.hexdigest(),
            uploaded_by=uploaded_by,
        )
    except Exception:
        # Never leave a stored file with no database row pointing at it.
        storage.delete(storage_key)
        raise


@transaction.atomic
def record_programming(*, fleet, radio, version, programmed_at, recorded_by, note=""):
    if radio.fleet_id != fleet.id or version.fleet_id != fleet.id:
        raise CrossFleetError("Radio and version must both belong to the fleet being acted on.")
    if not version.is_published:
        raise VersionNotPublishedError("Only a published version can be recorded as programmed.")
    return ProgrammingRecord.objects.create(
        fleet=fleet,
        radio=radio,
        version=version,
        programmed_at=programmed_at,
        recorded_by=recorded_by,
        note=note,
    )

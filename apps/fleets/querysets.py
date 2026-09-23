from django.db import models


class ArchivableQuerySet(models.QuerySet):
    """Shared by any model with an `archived_at` field (Radio, Battery, Configuration)."""

    def active(self):
        return self.filter(archived_at__isnull=True)

    def archived(self):
        return self.filter(archived_at__isnull=False)

from django.contrib import admin

from .models import (
    ChannelSnapshot,
    Configuration,
    ConfigurationVersion,
    ProgrammingRecord,
    VersionAttachment,
)


class ChannelSnapshotInline(admin.TabularInline):
    model = ChannelSnapshot
    extra = 0


class VersionAttachmentInline(admin.TabularInline):
    model = VersionAttachment
    extra = 0
    readonly_fields = ("storage_key", "byte_size", "sha256", "uploaded_by", "uploaded_at")


@admin.register(Configuration)
class ConfigurationAdmin(admin.ModelAdmin):
    list_display = ("name", "fleet", "archived_at")
    list_filter = ("fleet",)
    search_fields = ("name",)


@admin.register(ConfigurationVersion)
class ConfigurationVersionAdmin(admin.ModelAdmin):
    list_display = ("configuration", "version_number", "label", "state", "published_at")
    list_filter = ("fleet", "state")
    inlines = [ChannelSnapshotInline, VersionAttachmentInline]


@admin.register(ProgrammingRecord)
class ProgrammingRecordAdmin(admin.ModelAdmin):
    list_display = ("radio", "version", "fleet", "programmed_at", "recorded_by")
    list_filter = ("fleet",)

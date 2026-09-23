from django.contrib import admin

from .models import Battery, BatteryAssignment, MaintenanceEvent, Radio


@admin.register(Radio)
class RadioAdmin(admin.ModelAdmin):
    list_display = ("asset_label", "fleet", "manufacturer", "model", "status", "archived_at")
    list_filter = ("fleet", "status", "purpose")
    search_fields = ("asset_label", "manufacturer", "model", "serial")


@admin.register(Battery)
class BatteryAdmin(admin.ModelAdmin):
    list_display = ("asset_label", "fleet", "maker", "model", "condition", "archived_at")
    list_filter = ("fleet", "condition")
    search_fields = ("asset_label", "maker", "model", "serial")


@admin.register(BatteryAssignment)
class BatteryAssignmentAdmin(admin.ModelAdmin):
    list_display = ("battery", "radio", "fleet", "started_at", "ended_at", "assigned_by")
    list_filter = ("fleet",)


@admin.register(MaintenanceEvent)
class MaintenanceEventAdmin(admin.ModelAdmin):
    list_display = ("radio", "fleet", "kind", "occurred_at", "recorded_by")
    list_filter = ("fleet", "kind")

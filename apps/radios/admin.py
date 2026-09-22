from django.contrib import admin

from .models import Radio


@admin.register(Radio)
class RadioAdmin(admin.ModelAdmin):
    list_display = ("asset_label", "fleet", "manufacturer", "model", "status", "archived_at")
    list_filter = ("fleet", "status", "purpose")
    search_fields = ("asset_label", "manufacturer", "model", "serial")

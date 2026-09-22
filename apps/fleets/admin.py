from django.contrib import admin

from .models import Fleet, Membership


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0


@admin.register(Fleet)
class FleetAdmin(admin.ModelAdmin):
    list_display = ("name", "created_by", "created_at")
    inlines = [MembershipInline]


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("fleet", "user", "role", "is_active")
    list_filter = ("role", "is_active")

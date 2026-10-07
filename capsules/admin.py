from django.contrib import admin
from .models import Capsule


@admin.register(Capsule)
class CapsuleAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "owner",
        "opens_at",
        "sealed_at",
        "created_at",
    )
    list_filter = ("opens_at", "sealed_at")
    search_fields = ("title", "owner__username")
    readonly_fields = (
        "id",
        "sealed_at",
        "first_opened_at",
        "created_at",
        "updated_at",
    )
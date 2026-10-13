from django.contrib import admin
from .models import Capsule
from .services import DRAFT_FIELDS, update_draft
from django.core.exceptions import PermissionDenied, ValidationError


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

    def get_readonly_fields(self, request, obj=None):
        fields = self.readonly_fields
        if obj:
            fields += ("owner",)
            if not obj.is_draft:
                fields += DRAFT_FIELDS
        return fields

    def has_change_permission(self, request, obj=None):
        if obj is not None and not obj.is_draft:
            return False
        return super().has_change_permission(request, obj)

    def save_model(self, request, obj, form, change):
        if change:
            # A seal can occur after the admin form was loaded or validated.
            try:
                update_draft(obj, {name: getattr(obj, name) for name in DRAFT_FIELDS})
            except ValidationError as exc:
                raise PermissionDenied(" ".join(exc.messages)) from exc
        else:
            super().save_model(request, obj, form, change)

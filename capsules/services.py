from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import Capsule, Reflection
from django.db import transaction
from django.db.models import F


DRAFT_FIELDS = ("title", "description", "message", "opens_at", "theme")
REFLECTION_FIELDS = ("changed", "fulfilled", "surprised")


def can_reflect(capsule):
    return not capsule.is_draft and capsule.first_opened_at is not None and capsule.opens_at <= timezone.now()


def save_reflection(capsule, values):
    with transaction.atomic():
        # Lock the parent without changing its content or edit timestamp.
        allowed = Capsule.objects.filter(
            pk=capsule.pk, owner_id=capsule.owner_id, sealed_at__isnull=False,
            first_opened_at__isnull=False, opens_at__lte=timezone.now(),
        ).update(updated_at=F("updated_at"))
        if not allowed:
            raise ValidationError("Reflecția este disponibilă doar după deschiderea capsulei.")
        if not any(values.get(name, "").strip() for name in REFLECTION_FIELDS):
            raise ValidationError("Scrie măcar un gând pentru această reflecție.")
        reflection, _ = Reflection.objects.update_or_create(
            capsule_id=capsule.pk, defaults={name: values[name] for name in REFLECTION_FIELDS},
        )
        return reflection


def update_draft(capsule, values):
    """A single conditional write cannot overwrite a concurrent seal."""
    now = timezone.now()
    if values["opens_at"] <= now:
        raise ValidationError("Alege o dată de deschidere din viitor.")
    updated = Capsule.objects.filter(pk=capsule.pk, sealed_at__isnull=True).update(
        **{name: values[name] for name in DRAFT_FIELDS}, updated_at=now,
    )
    if not updated:
        raise ValidationError("Capsula a fost sigilată sau ștearsă între timp. Reîncarcă lista.")


def seal_capsule(capsule):
    """Compare the validated snapshot and seal atomically on both supported DBs."""
    if capsule.sealed_at is not None:
        return False
    now = timezone.now()
    if capsule.opens_at <= now:
        raise ValidationError("Alege o dată viitoare înainte de sigilare.")
    if not capsule.message.strip():
        raise ValidationError("Scrie un mesaj înainte de a sigila capsula.")
    snapshot = {name: getattr(capsule, name) for name in DRAFT_FIELDS}
    changed = Capsule.objects.filter(
        pk=capsule.pk, owner_id=capsule.owner_id, sealed_at__isnull=True,
        opens_at__gt=now, **snapshot,
    ).update(sealed_at=now, updated_at=now)
    if not changed:
        if Capsule.objects.filter(pk=capsule.pk, sealed_at__isnull=False).exists():
            return False
        raise ValidationError("Capsula a fost modificată între timp. Verifică datele și încearcă din nou.")
    return True

from dataclasses import dataclass
from io import BytesIO
import logging
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import Attachment, Capsule, PendingFileDeletion, attachment_path
from .storage import private_photo_storage


MAX_PHOTOS = 10
MAX_BYTES = 5 * 1024 * 1024
MAX_SIDE = 12000
MAX_PIXELS = 25_000_000
FORMATS = {"JPEG": ("jpg", "image/jpeg"), "PNG": ("png", "image/png"), "WEBP": ("webp", "image/webp")}
logger = logging.getLogger(__name__)


@dataclass
class ValidatedPhoto:
    data: bytes
    extension: str
    content_type: str
    width: int
    height: int
    original_name: str


def validate_photo(upload):
    if upload.size > MAX_BYTES:
        raise ValidationError("Fiecare fotografie poate avea cel mult 5 MB.")
    upload.seek(0)
    data = upload.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValidationError("Fiecare fotografie poate avea cel mult 5 MB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                fmt = image.format
                if fmt not in FORMATS:
                    raise ValidationError("Sunt acceptate doar imagini JPEG, PNG și WebP.")
                width, height = image.size
                if width > MAX_SIDE or height > MAX_SIDE or width * height > MAX_PIXELS:
                    raise ValidationError("Imaginea poate avea cel mult 25 megapixeli și 12000 px pe latură.")
                if getattr(image, "n_frames", 1) != 1:
                    raise ValidationError("Alege o fotografie statică, fără animație.")
                image.verify()
            # Decode and re-encode pixels: discard EXIF/GPS and appended payloads.
            with Image.open(BytesIO(data)) as image:
                image.load()
                normalized = ImageOps.exif_transpose(image)
                has_alpha = "A" in normalized.getbands() or "transparency" in normalized.info
                normalized = normalized.convert("RGBA" if has_alpha and fmt != "JPEG" else "RGB")
                width, height = normalized.size
                normalized.info.clear()
                output = BytesIO()
                normalized.save(output, format=fmt)
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValidationError("Fișierul nu este o imagine validă sau este deteriorat.") from exc
    data = output.getvalue()
    if len(data) > MAX_BYTES:
        raise ValidationError("Imaginea normalizată depășește limita de 5 MB.")
    extension, content_type = FORMATS[fmt]
    original_name = upload.name.replace("\\", "/").rsplit("/", 1)[-1][:150]
    return ValidatedPhoto(data, extension, content_type, width, height, original_name)


def attempt_file_deletion(pk):
    job = PendingFileDeletion.objects.filter(pk=pk).first()
    if job is None:
        return True
    try:
        private_photo_storage.delete(job.name)
    except Exception as exc:
        PendingFileDeletion.objects.filter(pk=pk).update(attempts=F("attempts") + 1, last_error=type(exc).__name__)
        logger.warning("Private photo cleanup failed; queued for retry (job %s).", pk)
        return False
    job.delete()
    return True


def schedule_file_deletion(name):
    job, _ = PendingFileDeletion.objects.get_or_create(name=name)
    transaction.on_commit(lambda: attempt_file_deletion(job.pk), robust=True)


def lock_draft(capsule):
    # Acquire the parent's write lock before counting/writing attachments.
    # SQLite serializes writers; PostgreSQL locks this row until commit.
    if not Capsule.objects.filter(pk=capsule.pk, owner_id=capsule.owner_id, sealed_at__isnull=True).update(updated_at=timezone.now()):
        raise ValidationError("Fotografiile pot fi modificate doar cât timp capsula este o ciornă.")


def _write_photos(capsule, photos, saved_names):
    for photo in photos:
        attachment = Attachment(
            capsule=capsule, original_name=photo.original_name,
            content_type=photo.content_type, width=photo.width, height=photo.height,
            size=len(photo.data),
        )
        name = attachment_path(attachment, f"photo.{photo.extension}")
        if not private_photo_storage.exists(name):
            saved_names.append(name)
        saved = private_photo_storage.save(name, ContentFile(photo.data))
        if saved != name:
            saved_names.append(saved)
        attachment.file = saved
        attachment.save(force_insert=True)


def add_photos(capsule, photos):
    saved_names = []
    try:
        with transaction.atomic():
            lock_draft(capsule)
            if capsule.attachments.count() + len(photos) > MAX_PHOTOS:
                raise ValidationError("O capsulă poate avea cel mult 10 fotografii.")
            _write_photos(capsule, photos, saved_names)
    except Exception:
        for name in saved_names:
            schedule_file_deletion(name)
        raise


def remove_photo(attachment):
    with transaction.atomic():
        lock_draft(attachment.capsule)
        attachment.delete()


def save_capsule_with_photos(capsule, values, photos=(), remove_ids=()):
    """Commit the draft, additions and removals together; compensate file writes."""
    from .services import DRAFT_FIELDS, update_draft

    saved_names = []
    try:
        with transaction.atomic():
            if values["opens_at"] <= timezone.now():
                raise ValidationError("Alege o dată de deschidere din viitor.")
            if capsule._state.adding:
                for name in DRAFT_FIELDS:
                    setattr(capsule, name, values[name])
                capsule.save(force_insert=True)
            else:
                # This conditional UPDATE holds the same parent lock as uploads.
                update_draft(capsule, values)
            remove_ids = set(remove_ids)
            removals = capsule.attachments.filter(pk__in=remove_ids)
            if removals.count() != len(remove_ids):
                raise ValidationError("Fotografiile au fost modificate între timp. Reîncarcă formularul.")
            removals.delete()
            if capsule.attachments.count() + len(photos) > MAX_PHOTOS:
                raise ValidationError("O capsulă poate avea cel mult 10 fotografii.")
            _write_photos(capsule, photos, saved_names)
    except Exception:
        for name in saved_names:
            schedule_file_deletion(name)
        raise
    return capsule

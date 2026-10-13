from datetime import timedelta
from uuid import uuid4

from django.core import signing
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from .models import User, VerifiedEmail

SALT = "accounts.email-verification"
MAX_AGE = 3600


def send_verification(user, email, request):
    email = email.strip().casefold()
    now = timezone.now()
    nonce = uuid4()
    with transaction.atomic():
        updated = User.objects.filter(pk=user.pk, is_active=True).filter(
            Q(email_verification_sent_at__isnull=True) |
            Q(email_verification_sent_at__lte=now - timedelta(seconds=60))
        ).update(pending_email=email, email_verification_nonce=nonce, email_verification_sent_at=now)
        if not updated:
            raise ValidationError("Așteaptă un minut înainte de a solicita un nou link.")
        if VerifiedEmail.objects.filter(email=email).exclude(user=user).exists():
            raise ValidationError("Adresa nu este disponibilă. Folosește o altă adresă.")
        current = User.objects.get(pk=user.pk)
        token = signing.dumps({"user": user.pk, "email": email, "current_email": current.email, "nonce": str(nonce)}, salt=SALT)
        link = request.build_absolute_uri(reverse("accounts:email_confirm", args=[token]))
        body = render_to_string("accounts/email_verification.txt", {"username": user.username, "link": link})
        EmailMessage("Confirmă adresa de email · Time Capsule", body, to=[email]).send()


def confirmation_data(user, token):
    try:
        data = signing.loads(token, salt=SALT, max_age=MAX_AGE)
        if data["user"] != user.pk or not user.is_active:
            return None
        if str(user.email_verification_nonce) != data["nonce"] or user.pending_email != data["email"] or user.email != data["current_email"]:
            return None
        return data
    except (signing.BadSignature, KeyError, TypeError):
        return None


def confirm_email(user, token):
    try:
        with transaction.atomic():
            # Conditional write serializes consumption, including on SQLite.
            data = confirmation_data(User.objects.get(pk=user.pk), token)
            if not data:
                raise ValidationError("Linkul este invalid, expirat sau deja folosit.")
            updated = User.objects.filter(pk=user.pk, is_active=True, email=data["current_email"], email_verification_nonce=data["nonce"], pending_email=data["email"]).update(
                email=data["email"], pending_email="", email_verification_nonce=None,
            )
            if not updated:
                raise ValidationError("Linkul nu mai este disponibil.")
            VerifiedEmail.objects.update_or_create(user=user, defaults={"email": data["email"], "verified_at": timezone.now()})
    except IntegrityError as exc:
        raise ValidationError("Adresa a fost confirmată pentru alt cont. Folosește o altă adresă.") from exc

from django.contrib.auth import login, logout
from django.shortcuts import redirect, render
from .forms import AccountDeletionForm, ProfileForm, SignUpForm
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from django.core.exceptions import ValidationError
from capsules.models import Attachment, Reflection
from .services import delete_account, save_profile
from django.http import FileResponse, Http404
from django.views.decorators.http import require_safe
import logging


@login_required
@never_cache
@require_safe
def avatar_image(request):
    if not request.user.avatar:
        raise Http404("Nu există o fotografie de profil.")
    try:
        image = request.user.avatar.open("rb")
    except FileNotFoundError as exc:
        raise Http404("Fotografia nu a fost găsită.") from exc
    return FileResponse(image, content_type="image/png", filename="avatar.png")


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def account_delete(request):
    form = AccountDeletionForm(request.POST if request.method == "POST" else None, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            delete_account(request.user)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            logout(request)
            messages.success(request, "Contul tău a fost șters.")
            return redirect("capsules:home")
    return render(request, "accounts/account_confirm_delete.html", {
        "form": form,
        "capsule_count": request.user.capsules.count(),
        "photo_count": Attachment.objects.filter(capsule__owner=request.user).count(),
        "reflection_count": Reflection.objects.filter(capsule__owner=request.user).count(),
    })


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def profile(request):
    next_url = request.POST.get("next") if request.method == "POST" else request.GET.get("next")
    if not next_url or not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
    ):
        next_url = reverse("accounts:profile")
    form = ProfileForm(request.POST if request.method == "POST" else None, request.FILES if request.method == "POST" else None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            save_profile(request.user, {name: form.cleaned_data[name] for name in ProfileForm.Meta.fields}, form.cleaned_data["avatar_upload"], form.cleaned_data["remove_avatar"])
        except ValidationError as exc:
            form.add_error(None, exc)
        except OSError:
            logging.getLogger(__name__).exception("Profile avatar save failed.")
            form.add_error(None, "Profilul nu a putut fi salvat. Selectează din nou fotografia și încearcă din nou.")
        else:
            messages.success(request, "Preferințele tale au fost salvate.")
            return redirect(next_url)
    return render(request, "accounts/profile.html", {"form": form, "next_url": next_url})


def signup(request):
    if request.user.is_authenticated:
        return redirect("capsules:home")
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("capsules:home")
    else:
        form = SignUpForm()
    return render(request, "accounts/signup.html", {"form": form})


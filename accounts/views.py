from django.contrib.auth import login
from django.shortcuts import redirect, render
from .forms import ProfileForm, SignUpForm
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def profile(request):
    next_url = request.POST.get("next") if request.method == "POST" else request.GET.get("next")
    if not next_url or not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
    ):
        next_url = reverse("capsules:list")
    form = ProfileForm(request.POST if request.method == "POST" else None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        user = form.save(commit=False)
        user.save(update_fields=ProfileForm.Meta.fields)
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


from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .models import Capsule
from zoneinfo import ZoneInfo
from django.shortcuts import redirect
from django.utils import timezone
from .forms import CapsuleForm
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.db.models import Case, When, Value, CharField, Count, Q
from math import ceil
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.core.exceptions import ValidationError
from .services import DRAFT_FIELDS, seal_capsule, update_draft


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def capsule_seal(request, pk):
    capsule = get_object_or_404(Capsule, pk=pk, owner=request.user)
    error = None
    if request.method == "POST":
        try:
            changed = seal_capsule(capsule)
            url = reverse("capsules:detail", args=[pk])
            return redirect(f"{url}?sealed=1" if changed else url)
        except ValidationError as exc:
            error = " ".join(exc.messages)
    with timezone.override(ZoneInfo(request.user.timezone)):
        return render(request, "capsules/capsule_confirm_seal.html", {"capsule": capsule, "error": error})


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def capsule_detail(request, pk):
    capsule = get_object_or_404(Capsule, pk=pk, owner=request.user)
    now = timezone.now()
    if request.method == "POST":
        if capsule.is_draft or capsule.opens_at > now:
            return HttpResponseForbidden("Această capsulă nu poate fi deschisă încă.")
        # Conditional UPDATE is atomic on SQLite and PostgreSQL; repeated opens
        # cannot replace the original timestamp.
        changed = Capsule.objects.filter(
            pk=pk, owner=request.user, sealed_at__isnull=False,
            opens_at__lte=now, first_opened_at__isnull=True,
        ).update(first_opened_at=now)
        url = reverse("capsules:detail", args=[pk])
        return redirect(f"{url}?opened=1" if changed else url)
    can_read = capsule.is_draft or (
        capsule.opens_at <= now and capsule.first_opened_at is not None
    )
    with timezone.override(ZoneInfo(request.user.timezone)):
        return render(request, "capsules/capsule_detail.html", {
            "capsule": capsule, "can_read": can_read,
            "can_open": not capsule.is_draft and capsule.opens_at <= now,
            "animate_open": can_read and not capsule.is_draft and request.GET.get("opened") == "1",
            "animate_seal": not capsule.is_draft and request.GET.get("sealed") == "1",
        })


@login_required
@require_http_methods(["GET", "POST"])
def capsule_delete(request, pk):
    capsule = get_object_or_404(Capsule, pk=pk, owner=request.user)
    if request.method == "POST":
        capsule.delete()
        messages.success(request, "Capsula a fost ștearsă.")
        return redirect("capsules:list")
    return render(request, "capsules/capsule_confirm_delete.html", {"capsule": capsule})

def home(request):
    return render(request, "capsules/home.html")

@login_required
def capsule_list(request):
    now = timezone.now()
    owned = Capsule.objects.filter(owner=request.user).annotate(
        ui_state=Case(
            When(sealed_at__isnull=True, then=Value("draft")),
            When(first_opened_at__isnull=False, then=Value("opened")),
            When(opens_at__lte=now, then=Value("available")),
            default=Value("sealed"), output_field=CharField(),
        )
    )
    query = request.GET.get("q", "").strip()[:200]
    if query:
        owned = owned.filter(Q(title__icontains=query) | Q(description__icontains=query))
    counts = dict(owned.order_by().values_list("ui_state").annotate(total=Count("pk")))
    labels = [("all", "Toate"), ("draft", "Ciorne"), ("sealed", "Sigilate"),
              ("available", "Disponibile"), ("opened", "Deschise")]
    selected = request.GET.get("state", "all")
    if selected not in dict(labels):
        selected = "all"
    capsules = owned if selected == "all" else owned.filter(ui_state=selected)
    for capsule in capsules:
        seconds = (capsule.opens_at - now).total_seconds()
        if capsule.ui_state == "opened":
            capsule.opening_label = "O amintire redescoperită"
        elif seconds <= 0:
            capsule.opening_label = "Pregătită de deschidere" if capsule.ui_state == "available" else "Alege o nouă dată"
        elif seconds < 86400:
            capsule.opening_label = "Se deschide în mai puțin de o zi"
        else:
            days = ceil(seconds / 86400)
            unit = "de zile" if days % 100 == 0 or days % 100 >= 20 else "zile"
            capsule.opening_label = f"Se deschide peste {days} {unit}"
        if capsule.ui_state == "draft" and seconds > 0:
            capsule.opening_label = capsule.opening_label.replace("Se deschide", "Planificată")
    filters = [{"value": key, "label": label,
                "count": sum(counts.values()) if key == "all" else counts.get(key, 0)}
               for key, label in labels]
    with timezone.override(ZoneInfo(request.user.timezone)):
        return render(request, "capsules/capsule_list.html", {
            "capsules": capsules, "filters": filters, "selected_state": selected, "query": query,
        })

@login_required
def capsule_create(request):
    with timezone.override(ZoneInfo(request.user.timezone)):
        if request.method == "POST":
            form = CapsuleForm(request.POST)

            if form.is_valid():
                capsule = form.save(commit=False)
                capsule.owner = request.user
                capsule.save()

                return redirect("capsules:list")
        else:
            form = CapsuleForm()

        return render(
            request,
            "capsules/capsule_form.html",
            {"form": form},
        )

@login_required
def capsule_edit(request, pk):
    capsule = get_object_or_404(
        Capsule,
        pk=pk,
        owner=request.user,
    )

    if not capsule.is_draft:
        return HttpResponseForbidden(
            "O capsulă sigilată nu poate fi modificată."
        )
    with timezone.override(ZoneInfo(request.user.timezone)):
        if request.method == "POST":
            form = CapsuleForm(request.POST, instance=capsule)
            if form.is_valid():
                try:
                    update_draft(capsule, {name: form.cleaned_data[name] for name in DRAFT_FIELDS})
                except ValidationError as exc:
                    return HttpResponseForbidden(" ".join(exc.messages))
                return redirect("capsules:list")
        else:
            form = CapsuleForm(instance=capsule)
        return render(
            request,
            "capsules/capsule_form.html",
            {
                "form": form,
                "is_edit": True,
            },
        )


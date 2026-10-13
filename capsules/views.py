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
    capsules = Capsule.objects.filter(owner=request.user)
    return render(
        request,
        "capsules/capsule_list.html",
        {"capsules": capsules},
    )

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
                form.save()
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


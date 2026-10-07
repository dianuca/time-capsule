from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .models import Capsule
from zoneinfo import ZoneInfo
from django.shortcuts import redirect
from django.utils import timezone
from .forms import CapsuleForm
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404

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


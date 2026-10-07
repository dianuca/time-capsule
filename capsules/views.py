from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .models import Capsule


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


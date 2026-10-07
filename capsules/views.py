from django.shortcuts import render


def home(request):
    return render(request, "capsules/home.html")
from django.urls import path

from . import views

app_name = "capsules"
urlpatterns = [
    path("", views.home, name="home"),
]
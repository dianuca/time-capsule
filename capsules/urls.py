from django.urls import path

from . import views

app_name = "capsules"
urlpatterns = [
    path("", views.home, name="home"),
    path("capsules/", views.capsule_list, name="list"),
    path("capsules/new/", views.capsule_create, name="create"),
]

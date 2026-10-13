from django.urls import path

from . import views

app_name = "capsules"
urlpatterns = [
    path("", views.home, name="home"),
    path("capsules/", views.capsule_list, name="list"),
    path("capsules/new/", views.capsule_create, name="create"),
    path("capsules/<uuid:pk>/delete/", views.capsule_delete, name="delete"),
    path("capsules/<uuid:pk>/", views.capsule_detail, name="detail"),
    path("capsules/<uuid:pk>/seal/", views.capsule_seal, name="seal"),
    path("capsules/<uuid:pk>/reflection/", views.capsule_reflection, name="reflection"),
    path("capsules/<uuid:pk>/reflection/new/", views.capsule_from_reflection, name="from-reflection"),
    path("capsules/<uuid:pk>/photos/", views.capsule_photos, name="photos"),
    path("capsules/<uuid:pk>/photos/<uuid:attachment_pk>/", views.attachment_image, name="image"),
    path("capsules/<uuid:pk>/photos/<uuid:attachment_pk>/delete/", views.attachment_delete, name="photo-delete"),
    path(
    "capsules/<uuid:pk>/edit/",
    views.capsule_edit,
    name="edit",
),
]

from django.contrib.auth.views import LoginView, LogoutView, PasswordResetView, PasswordResetDoneView, PasswordResetConfirmView, PasswordResetCompleteView
from django.urls import path, reverse_lazy
from .forms import ResetPasswordForm
from . import views

app_name = "accounts"

urlpatterns = [
    path("email/", views.email_settings, name="email_settings"),
    path("email/confirm/<str:token>/", views.email_confirm, name="email_confirm"),
    path("password/reset/", PasswordResetView.as_view(template_name="accounts/password_reset.html", email_template_name="accounts/password_reset_email.txt", subject_template_name="accounts/password_reset_subject.txt", success_url=reverse_lazy("accounts:password_reset_done")), name="password_reset"),
    path("password/reset/sent/", PasswordResetDoneView.as_view(template_name="accounts/password_reset_done.html"), name="password_reset_done"),
    path("password/reset/<uidb64>/<token>/", PasswordResetConfirmView.as_view(template_name="accounts/password_reset_confirm.html", form_class=ResetPasswordForm, success_url=reverse_lazy("accounts:password_reset_complete")), name="password_reset_confirm"),
    path("password/changed/", PasswordResetCompleteView.as_view(template_name="accounts/password_reset_complete.html"), name="password_reset_complete"),
    path("signup/", views.signup, name="signup"),
    path("profile/", views.profile, name="profile"),
    path("avatar/", views.avatar_image, name="avatar"),
    path("delete/", views.account_delete, name="delete"),
    path(
        "login/",
        LoginView.as_view(
            template_name="accounts/login.html",
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
    path("logout/", LogoutView.as_view(), name="logout"),
]

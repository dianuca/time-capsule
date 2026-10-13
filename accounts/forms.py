from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User
from zoneinfo import available_timezones
from capsules.photo_services import validate_photo


class AccountDeletionForm(forms.Form):
    password = forms.CharField(
        label="Parola curentă", strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
        error_messages={"required": "Introdu parola curentă."},
    )
    confirm = forms.BooleanField(
        label="Înțeleg că acest cont și toate amintirile lui vor fi șterse definitiv.",
        error_messages={"required": "Bifează confirmarea înainte de ștergere."},
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_password(self):
        password = self.cleaned_data["password"]
        if not self.user.check_password(password):
            raise forms.ValidationError("Parola nu este corectă.")
        return password


class ProfileForm(forms.ModelForm):
    avatar_upload = forms.FileField(
        required=False, label="Schimbă fotografia",
        widget=forms.FileInput(attrs={"accept": "image/jpeg,image/png,image/webp", "form": "profile-form"}),
    )
    remove_avatar = forms.BooleanField(required=False, label="Revino la avatarul implicit", widget=forms.CheckboxInput(attrs={"form": "profile-form"}))
    timezone = forms.ChoiceField(
        label="Fus orar", choices=[(name, name.replace("_", " ")) for name in sorted(available_timezones())],
        help_text="Datele capsulelor sunt afișate și introduse în acest fus orar.",
    )

    class Meta:
        model = User
        fields = ("first_name", "last_name", "timezone", "email_notifications_enabled")
        labels = {"first_name": "Prenume", "last_name": "Nume", "email_notifications_enabled": "Notificări prin email"}
        widgets = {
            "first_name": forms.TextInput(attrs={"autocomplete": "given-name"}),
            "last_name": forms.TextInput(attrs={"autocomplete": "family-name"}),
        }

    def clean_avatar_upload(self):
        upload = self.cleaned_data.get("avatar_upload")
        return validate_photo(upload) if upload else None

    def clean(self):
        data = super().clean()
        if data.get("avatar_upload") and data.get("remove_avatar"):
            raise forms.ValidationError("Alege o fotografie nouă sau revenirea la avatarul implicit.")
        return data

class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True, label="Email")
    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User
from zoneinfo import available_timezones


class ProfileForm(forms.ModelForm):
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

class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True, label="Email")
    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

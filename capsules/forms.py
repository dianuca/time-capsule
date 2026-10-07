from django import forms
from django.utils import timezone
from .models import Capsule

class CapsuleForm(forms.ModelForm):
    class Meta:
        model = Capsule
        fields = ("title", "description", "message", "opens_at")
        labels = {
            "title": "Titlu",
            "description": "Descriere scurtă",
            "message": "Mesaj pentru viitor",
            "opens_at": "Data și ora deschiderii",
        }
        widgets = {
            "title": forms.TextInput(
                attrs={"placeholder": "Pentru mine, peste un an"}
            ),
            "description": forms.TextInput(
                attrs={"placeholder": "Despre ce este această capsulă?"}
            ),
            "message": forms.Textarea(attrs={"rows": 7}),
            "opens_at": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={"type": "datetime-local"},
            ),
        }

    def clean_opens_at(self):
        opens_at = self.cleaned_data["opens_at"]
        if opens_at <= timezone.now():
            raise forms.ValidationError(
                "Alege o dată de deschidere din viitor."
            )
        return opens_at


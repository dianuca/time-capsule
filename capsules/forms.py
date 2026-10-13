from django import forms
from django.utils import timezone
from .models import Capsule

class CapsuleForm(forms.ModelForm):
    class Meta:
        model = Capsule
        fields = ("title", "description", "message", "opens_at", "theme")
        labels = {
            "title": "Titlu",
            "description": "Descriere scurtă",
            "message": "Ce vrei să-i spui versiunii tale din viitor?",
            "opens_at": "Data și ora deschiderii",
            "theme": "Culoarea amintirii",
        }
        widgets = {
            "theme": forms.RadioSelect(),
            "title": forms.TextInput(
                attrs={"placeholder": "Pentru mine, peste un an"}
            ),
            "description": forms.TextInput(
                attrs={"placeholder": "Despre ce este această capsulă?"}
            ),
            "message": forms.Textarea(attrs={"rows": 7, "placeholder": "Dragă eu din viitor, astăzi…"}),
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["theme"].required = False

    def clean_theme(self):
        return self.cleaned_data.get("theme") or self.instance.theme


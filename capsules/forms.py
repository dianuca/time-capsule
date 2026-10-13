from django import forms
from django.utils import timezone
from .models import Capsule
from .photo_services import MAX_PHOTOS, validate_photo


class MultiplePhotoInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class PhotoFilesField(forms.FileField):
    def clean(self, data, initial=None):
        if not data:
            raise forms.ValidationError("Alege cel puțin o fotografie.")
        uploads = data if isinstance(data, (list, tuple)) else [data]
        if len(uploads) > MAX_PHOTOS:
            raise forms.ValidationError("Alege cel mult 10 fotografii.")
        return [validate_photo(super(PhotoFilesField, self).clean(upload, initial)) for upload in uploads]


class PhotoUploadForm(forms.Form):
    photos = PhotoFilesField(
        label="Adaugă fotografii",
        widget=MultiplePhotoInput(attrs={"accept": "image/jpeg,image/png,image/webp"}),
    )

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


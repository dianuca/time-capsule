from django import forms
from django.utils import timezone
from .models import Attachment, Capsule, Reflection
from .photo_services import MAX_PHOTOS, validate_photo


class MultiplePhotoInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class PhotoFilesField(forms.FileField):
    def clean(self, data, initial=None):
        if not data:
            if self.required:
                raise forms.ValidationError("Alege cel puțin o fotografie.")
            return []
        uploads = data if isinstance(data, (list, tuple)) else [data]
        if len(uploads) > MAX_PHOTOS:
            raise forms.ValidationError("Alege cel mult 10 fotografii.")
        return [validate_photo(super(PhotoFilesField, self).clean(upload, initial)) for upload in uploads]


class PhotoUploadForm(forms.Form):
    photos = PhotoFilesField(
        label="Adaugă fotografii",
        widget=MultiplePhotoInput(attrs={"accept": "image/jpeg,image/png,image/webp"}),
    )


class ReflectionForm(forms.ModelForm):
    class Meta:
        model = Reflection
        fields = ("changed", "fulfilled", "surprised")
        labels = {
            "changed": "Ce s-a schimbat de atunci?",
            "fulfilled": "Ce s-a împlinit?",
            "surprised": "Ce te-a surprins?",
        }
        widgets = {name: forms.Textarea(attrs={"rows": 4}) for name in fields}

    def clean(self):
        data = super().clean()
        if not any(data.get(name, "").strip() for name in self.Meta.fields):
            raise forms.ValidationError("Scrie măcar un gând pentru această reflecție.")
        return data

class CapsuleForm(forms.ModelForm):
    photos = PhotoFilesField(
        required=False, label="Fotografii",
        widget=MultiplePhotoInput(attrs={"accept": "image/jpeg,image/png,image/webp", "data-photo-input": ""}),
    )
    remove_photos = forms.ModelMultipleChoiceField(
        required=False, queryset=Attachment.objects.none(), widget=forms.CheckboxSelectMultiple,
    )
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
        self.fields["remove_photos"].queryset = self.instance.attachments.all() if not self.instance._state.adding else Attachment.objects.none()

    def clean_theme(self):
        return self.cleaned_data.get("theme") or self.instance.theme

    @property
    def photo_cards(self):
        selected = {str(value) for value in (self["remove_photos"].value() or [])}
        return [{"attachment": photo, "removed": str(photo.pk) in selected}
                for photo in self.fields["remove_photos"].queryset]

    def clean(self):
        data = super().clean()
        if "photos" in data and "remove_photos" in data:
            existing = self.instance.attachments.count() if not self.instance._state.adding else 0
            if existing - len(data["remove_photos"]) + len(data["photos"]) > MAX_PHOTOS:
                raise forms.ValidationError("O capsulă poate avea cel mult 10 fotografii. Elimină una pentru a adăuga alta.")
        return data


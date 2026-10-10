from django import forms
from django.conf import settings


class UploadCSVForm(forms.Form):
    file = forms.FileField(
        label="CSV file",
        widget=forms.ClearableFileInput(attrs={"accept": ".csv"}),
    )

    def clean_file(self):
        f = self.cleaned_data["file"]
        if not f.name.lower().endswith(".csv"):
            raise forms.ValidationError("Only .csv files are supported.")
        max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
        if f.size > max_bytes:
            raise forms.ValidationError(f"File too large (max {settings.MAX_UPLOAD_MB} MB).")
        return f
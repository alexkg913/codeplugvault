from django import forms

from .models import Radio


class RadioForm(forms.ModelForm):
    class Meta:
        model = Radio
        fields = [
            "asset_label",
            "manufacturer",
            "model",
            "serial",
            "radio_id",
            "band",
            "firmware",
            "purpose",
            "status",
            "notes",
        ]

    def __init__(self, *args, fleet, **kwargs):
        # `fleet` is never a form field: it comes from the URL/membership check,
        # never from submitted data, so a cross-fleet asset label can't be forged.
        self.fleet = fleet
        super().__init__(*args, **kwargs)

    def clean_asset_label(self):
        asset_label = self.cleaned_data["asset_label"]
        qs = Radio.objects.filter(fleet=self.fleet, asset_label=asset_label)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(
                "A radio with this asset label already exists in this fleet."
            )
        return asset_label

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.fleet = self.fleet
        if commit:
            instance.save()
        return instance

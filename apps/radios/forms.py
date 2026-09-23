from django import forms

from .models import Battery, MaintenanceEvent, Radio


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


class BatteryForm(forms.ModelForm):
    class Meta:
        model = Battery
        fields = [
            "asset_label",
            "maker",
            "model",
            "serial",
            "chemistry",
            "capacity",
            "condition",
            "notes",
        ]

    def __init__(self, *args, fleet, **kwargs):
        self.fleet = fleet
        super().__init__(*args, **kwargs)

    def clean_asset_label(self):
        asset_label = self.cleaned_data["asset_label"]
        qs = Battery.objects.filter(fleet=self.fleet, asset_label=asset_label)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(
                "A battery with this asset label already exists in this fleet."
            )
        return asset_label

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.fleet = self.fleet
        if commit:
            instance.save()
        return instance


class BatteryAssignForm(forms.Form):
    battery = forms.ModelChoiceField(queryset=Battery.objects.none(), label="Battery")
    note = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"rows": 2}), label="Note (optional)"
    )

    def __init__(self, *args, fleet, **kwargs):
        super().__init__(*args, **kwargs)
        # Scoping the queryset to this fleet is what stops a forged battery id
        # from another fleet ever validating, regardless of what's posted.
        self.fields["battery"].queryset = Battery.objects.filter(
            fleet=fleet, archived_at__isnull=True
        )


class MaintenanceEventForm(forms.ModelForm):
    class Meta:
        model = MaintenanceEvent
        fields = ["kind", "occurred_at", "notes"]
        widgets = {"occurred_at": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, fleet, radio, **kwargs):
        self.fleet = fleet
        self.radio = radio
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.fleet = self.fleet
        instance.radio = self.radio
        if commit:
            instance.save()
        return instance

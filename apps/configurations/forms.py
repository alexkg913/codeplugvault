from django import forms
from django.utils import timezone

from .models import ChannelSnapshot, Configuration, ConfigurationVersion, ProgrammingRecord


class ConfigurationForm(forms.ModelForm):
    class Meta:
        model = Configuration
        fields = ["name", "description", "compatibility_notes"]

    def __init__(self, *args, fleet, **kwargs):
        self.fleet = fleet
        super().__init__(*args, **kwargs)

    def clean_name(self):
        name = self.cleaned_data["name"]
        qs = Configuration.objects.filter(fleet=self.fleet, name=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(
                "A configuration with this name already exists in this fleet."
            )
        return name

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.fleet = self.fleet
        if commit:
            instance.save()
        return instance


class ConfigurationVersionForm(forms.Form):
    label = forms.CharField(max_length=150, required=False)
    release_notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))


class ChannelSnapshotForm(forms.ModelForm):
    class Meta:
        model = ChannelSnapshot
        fields = [
            "position",
            "zone",
            "name",
            "mode",
            "rx_frequency",
            "tx_frequency",
            "rx_tone",
            "tx_tone",
            "color_code",
            "timeslot",
            "notes",
        ]

    def __init__(self, *args, version, **kwargs):
        self.version = version
        super().__init__(*args, **kwargs)

    def clean_position(self):
        position = self.cleaned_data["position"]
        qs = ChannelSnapshot.objects.filter(version=self.version, position=position)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("A channel already occupies this position in this version.")
        return position

    def clean(self):
        cleaned = super().clean()
        if (
            cleaned.get("mode") == ChannelSnapshot.Mode.DIGITAL
            and cleaned.get("color_code") is None
        ):
            self.add_error("color_code", "Color code is required for digital channels.")
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.fleet = self.version.fleet
        instance.version = self.version
        if commit:
            instance.save()
        return instance


class VersionAttachmentUploadForm(forms.Form):
    file = forms.FileField(label="File")


class ProgrammingRecordForm(forms.ModelForm):
    programmed_at = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        input_formats=["%Y-%m-%dT%H:%M"],
    )

    class Meta:
        model = ProgrammingRecord
        fields = ["version", "programmed_at", "note"]

    def __init__(self, *args, fleet, radio, **kwargs):
        self.fleet = fleet
        self.radio = radio
        super().__init__(*args, **kwargs)
        # Only published versions are selectable: recording that a draft was
        # "programmed" wouldn't mean anything -- publishing is what freezes
        # the content a radio could actually be programmed with.
        self.fields["version"].queryset = ConfigurationVersion.objects.filter(
            fleet=fleet, state=ConfigurationVersion.State.PUBLISHED
        ).select_related("configuration")
        self.fields["version"].label_from_instance = (
            lambda v: f"{v.configuration.name} — {v.display_name}"
        )
        self.fields["programmed_at"].initial = timezone.now()

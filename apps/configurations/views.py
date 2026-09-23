from django.contrib import messages
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.fleets.mixins import FleetScopedMixin
from apps.radios.models import Radio

from .comparison import compare_versions
from .forms import (
    ChannelSnapshotForm,
    ConfigurationForm,
    ConfigurationVersionForm,
    ProgrammingRecordForm,
    VersionAttachmentUploadForm,
)
from .models import ChannelSnapshot, Configuration, ConfigurationVersion, VersionAttachment
from .services import (
    AttachmentUploadError,
    CrossFleetError,
    VersionNotDraftError,
    VersionNotPublishedError,
    create_version,
    get_attachment_storage,
    publish_version,
    record_programming,
    store_attachment,
)


class ConfigurationListView(FleetScopedMixin, ListView):
    template_name = "configurations/list.html"
    context_object_name = "configurations"
    paginate_by = 50
    active_tab = "configurations"

    def get_queryset(self):
        qs = Configuration.objects.filter(fleet=self.fleet)
        qs = qs.archived() if self.request.GET.get("archived") == "1" else qs.active()

        name = self.request.GET.get("name", "").strip()
        if name:
            qs = qs.filter(name__icontains=name)

        return qs.prefetch_related("versions")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["fleet"] = self.fleet
        ctx["membership"] = self.membership
        ctx["active_tab"] = self.active_tab
        ctx["show_archived"] = self.request.GET.get("archived") == "1"
        ctx["filters"] = self.request.GET
        return ctx


class ConfigurationDetailView(FleetScopedMixin, DetailView):
    template_name = "configurations/detail.html"
    context_object_name = "configuration"
    slug_field = "public_id"
    slug_url_kwarg = "public_id"
    active_tab = "configurations"

    def get_queryset(self):
        return Configuration.objects.filter(fleet=self.fleet)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["fleet"] = self.fleet
        ctx["membership"] = self.membership
        ctx["active_tab"] = self.active_tab
        ctx["versions"] = self.object.versions.select_related("created_by")
        return ctx


class ConfigurationCreateView(FleetScopedMixin, CreateView):
    require_editor = True
    template_name = "configurations/form.html"
    form_class = ConfigurationForm
    active_tab = "configurations"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["fleet"] = self.fleet
        return kwargs

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["fleet"] = self.fleet
        ctx["active_tab"] = self.active_tab
        return ctx

    def get_success_url(self):
        return reverse(
            "configurations:detail",
            kwargs={"fleet_public_id": self.fleet.public_id, "public_id": self.object.public_id},
        )


class ConfigurationUpdateView(FleetScopedMixin, UpdateView):
    require_editor = True
    template_name = "configurations/form.html"
    form_class = ConfigurationForm
    slug_field = "public_id"
    slug_url_kwarg = "public_id"
    active_tab = "configurations"

    def get_queryset(self):
        return Configuration.objects.filter(fleet=self.fleet)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["fleet"] = self.fleet
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["fleet"] = self.fleet
        ctx["active_tab"] = self.active_tab
        return ctx

    def get_success_url(self):
        return reverse(
            "configurations:detail",
            kwargs={"fleet_public_id": self.fleet.public_id, "public_id": self.object.public_id},
        )


class ConfigurationArchiveView(FleetScopedMixin, View):
    require_editor = True

    def post(self, request, fleet_public_id, public_id):
        configuration = get_object_or_404(Configuration, fleet=self.fleet, public_id=public_id)
        configuration.archived_at = timezone.now()
        configuration.save(update_fields=["archived_at", "updated_at"])
        messages.success(request, f"{configuration.name} archived.")
        return redirect("configurations:list", fleet_public_id=self.fleet.public_id)


class ConfigurationVersionCreateView(FleetScopedMixin, View):
    require_editor = True

    def get(self, request, fleet_public_id, public_id):
        configuration = get_object_or_404(Configuration, fleet=self.fleet, public_id=public_id)
        form = ConfigurationVersionForm()
        return render(
            request,
            "configurations/version_form.html",
            {
                "fleet": self.fleet,
                "active_tab": "configurations",
                "configuration": configuration,
                "form": form,
            },
        )

    def post(self, request, fleet_public_id, public_id):
        configuration = get_object_or_404(Configuration, fleet=self.fleet, public_id=public_id)
        form = ConfigurationVersionForm(request.POST)
        if form.is_valid():
            version = create_version(
                configuration=configuration,
                created_by=request.user,
                label=form.cleaned_data["label"],
                release_notes=form.cleaned_data["release_notes"],
            )
            messages.success(request, f"{version.display_name} created as a draft.")
            return redirect(
                "configurations:version-detail",
                fleet_public_id=self.fleet.public_id,
                public_id=version.public_id,
            )
        return render(
            request,
            "configurations/version_form.html",
            {
                "fleet": self.fleet,
                "active_tab": "configurations",
                "configuration": configuration,
                "form": form,
            },
        )


class ConfigurationVersionDetailView(FleetScopedMixin, DetailView):
    template_name = "configurations/version_detail.html"
    context_object_name = "version"
    slug_field = "public_id"
    slug_url_kwarg = "public_id"
    active_tab = "configurations"

    def get_queryset(self):
        return ConfigurationVersion.objects.filter(fleet=self.fleet).select_related(
            "configuration", "created_by"
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        version = self.object
        ctx["fleet"] = self.fleet
        ctx["membership"] = self.membership
        ctx["active_tab"] = self.active_tab
        ctx["channels"] = version.channels.all()
        ctx["attachments"] = version.attachments.select_related("uploaded_by")
        ctx["other_versions"] = version.configuration.versions.exclude(pk=version.pk)
        if self.membership.can_edit:
            ctx["attachment_form"] = VersionAttachmentUploadForm()
        return ctx


class ConfigurationVersionPublishView(FleetScopedMixin, View):
    require_editor = True

    def post(self, request, fleet_public_id, public_id):
        version = get_object_or_404(ConfigurationVersion, fleet=self.fleet, public_id=public_id)
        try:
            publish_version(version)
        except VersionNotDraftError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"{version.display_name} published.")
        return redirect(
            "configurations:version-detail",
            fleet_public_id=self.fleet.public_id,
            public_id=version.public_id,
        )


class DraftOnlyMixin:
    """Shared guard for channel mutation views: draft versions only."""

    def get_draft_version_or_redirect(self, request):
        version = get_object_or_404(
            ConfigurationVersion, fleet=self.fleet, public_id=self.kwargs["public_id"]
        )
        if not version.is_draft:
            messages.error(
                request,
                "Published version content can't be edited in place. Create a new version instead.",
            )
            return version, redirect(
                "configurations:version-detail",
                fleet_public_id=self.fleet.public_id,
                public_id=version.public_id,
            )
        return version, None


class ChannelSnapshotCreateView(FleetScopedMixin, DraftOnlyMixin, View):
    require_editor = True

    def get(self, request, fleet_public_id, public_id):
        version, redirect_response = self.get_draft_version_or_redirect(request)
        if redirect_response:
            return redirect_response
        form = ChannelSnapshotForm(version=version)
        return render(
            request,
            "configurations/channel_form.html",
            {"fleet": self.fleet, "active_tab": "configurations", "version": version, "form": form},
        )

    def post(self, request, fleet_public_id, public_id):
        version, redirect_response = self.get_draft_version_or_redirect(request)
        if redirect_response:
            return redirect_response
        form = ChannelSnapshotForm(request.POST, version=version)
        if form.is_valid():
            form.save()
            messages.success(request, "Channel added.")
            return redirect(
                "configurations:version-detail",
                fleet_public_id=self.fleet.public_id,
                public_id=version.public_id,
            )
        return render(
            request,
            "configurations/channel_form.html",
            {"fleet": self.fleet, "active_tab": "configurations", "version": version, "form": form},
        )


class ChannelSnapshotUpdateView(FleetScopedMixin, DraftOnlyMixin, View):
    require_editor = True

    def get(self, request, fleet_public_id, public_id, channel_id):
        version, redirect_response = self.get_draft_version_or_redirect(request)
        if redirect_response:
            return redirect_response
        channel = get_object_or_404(ChannelSnapshot, version=version, pk=channel_id)
        form = ChannelSnapshotForm(instance=channel, version=version)
        return render(
            request,
            "configurations/channel_form.html",
            {
                "fleet": self.fleet,
                "active_tab": "configurations",
                "version": version,
                "form": form,
                "channel": channel,
            },
        )

    def post(self, request, fleet_public_id, public_id, channel_id):
        version, redirect_response = self.get_draft_version_or_redirect(request)
        if redirect_response:
            return redirect_response
        channel = get_object_or_404(ChannelSnapshot, version=version, pk=channel_id)
        form = ChannelSnapshotForm(request.POST, instance=channel, version=version)
        if form.is_valid():
            form.save()
            messages.success(request, "Channel updated.")
            return redirect(
                "configurations:version-detail",
                fleet_public_id=self.fleet.public_id,
                public_id=version.public_id,
            )
        return render(
            request,
            "configurations/channel_form.html",
            {
                "fleet": self.fleet,
                "active_tab": "configurations",
                "version": version,
                "form": form,
                "channel": channel,
            },
        )


class ChannelSnapshotDeleteView(FleetScopedMixin, DraftOnlyMixin, View):
    require_editor = True

    def post(self, request, fleet_public_id, public_id, channel_id):
        version, redirect_response = self.get_draft_version_or_redirect(request)
        if redirect_response:
            return redirect_response
        channel = get_object_or_404(ChannelSnapshot, version=version, pk=channel_id)
        channel.delete()
        messages.success(request, "Channel removed.")
        return redirect(
            "configurations:version-detail",
            fleet_public_id=self.fleet.public_id,
            public_id=version.public_id,
        )


class VersionAttachmentUploadView(FleetScopedMixin, View):
    require_editor = True

    def post(self, request, fleet_public_id, public_id):
        version = get_object_or_404(ConfigurationVersion, fleet=self.fleet, public_id=public_id)
        form = VersionAttachmentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                store_attachment(
                    fleet=self.fleet,
                    version=version,
                    uploaded_file=form.cleaned_data["file"],
                    uploaded_by=request.user,
                )
            except AttachmentUploadError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, "File uploaded.")
        else:
            messages.error(request, "Choose a file to upload.")
        return redirect(
            "configurations:version-detail",
            fleet_public_id=self.fleet.public_id,
            public_id=version.public_id,
        )


class VersionAttachmentDownloadView(FleetScopedMixin, View):
    def get(self, request, fleet_public_id, public_id, attachment_id):
        version = get_object_or_404(ConfigurationVersion, fleet=self.fleet, public_id=public_id)
        attachment = get_object_or_404(
            VersionAttachment, fleet=self.fleet, version=version, pk=attachment_id
        )
        storage = get_attachment_storage()
        if not storage.exists(attachment.storage_key):
            raise Http404
        return FileResponse(
            storage.open(attachment.storage_key, "rb"),
            as_attachment=True,
            filename=attachment.original_filename,
        )


class VersionCompareView(FleetScopedMixin, View):
    def get(self, request, fleet_public_id, from_id, to_id):
        version_a = get_object_or_404(ConfigurationVersion, fleet=self.fleet, public_id=from_id)
        version_b = get_object_or_404(ConfigurationVersion, fleet=self.fleet, public_id=to_id)
        if version_a.configuration_id != version_b.configuration_id:
            messages.error(request, "You can only compare versions within the same configuration.")
            return redirect(
                "configurations:version-detail",
                fleet_public_id=self.fleet.public_id,
                public_id=version_a.public_id,
            )
        diff = compare_versions(version_a, version_b)
        return render(
            request,
            "configurations/version_compare.html",
            {
                "fleet": self.fleet,
                "membership": self.membership,
                "active_tab": "configurations",
                "version_a": version_a,
                "version_b": version_b,
                "diff": diff,
            },
        )


class ProgrammingRecordCreateView(FleetScopedMixin, View):
    require_editor = True

    def post(self, request, fleet_public_id, public_id):
        radio = get_object_or_404(Radio, fleet=self.fleet, public_id=public_id)
        form = ProgrammingRecordForm(request.POST, fleet=self.fleet, radio=radio)
        if form.is_valid():
            try:
                record_programming(
                    fleet=self.fleet,
                    radio=radio,
                    version=form.cleaned_data["version"],
                    programmed_at=form.cleaned_data["programmed_at"],
                    recorded_by=request.user,
                    note=form.cleaned_data["note"],
                )
            except (CrossFleetError, VersionNotPublishedError) as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, "Programming recorded.")
        else:
            messages.error(request, "Couldn't record that. Check the version and date.")
        return redirect(
            "radios:detail", fleet_public_id=self.fleet.public_id, public_id=radio.public_id
        )

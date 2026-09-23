from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.configurations.forms import ProgrammingRecordForm
from apps.fleets.mixins import FleetScopedMixin

from .forms import BatteryAssignForm, BatteryForm, MaintenanceEventForm, RadioForm
from .models import Battery, Radio
from .services import CrossFleetError, assign_battery, end_assignment


class RadioListView(FleetScopedMixin, ListView):
    template_name = "radios/list.html"
    context_object_name = "radios"
    paginate_by = 50
    active_tab = "radios"

    def get_queryset(self):
        qs = Radio.objects.filter(fleet=self.fleet)
        qs = qs.archived() if self.request.GET.get("archived") == "1" else qs.active()

        for field in ("asset_label", "manufacturer", "model"):
            value = self.request.GET.get(field, "").strip()
            if value:
                qs = qs.filter(**{f"{field}__icontains": value})

        status = self.request.GET.get("status", "").strip()
        if status:
            qs = qs.filter(status=status)

        purpose = self.request.GET.get("purpose", "").strip()
        if purpose:
            qs = qs.filter(purpose=purpose)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["fleet"] = self.fleet
        ctx["membership"] = self.membership
        ctx["active_tab"] = self.active_tab
        ctx["status_choices"] = Radio.Status.choices
        ctx["purpose_choices"] = Radio.Purpose.choices
        ctx["show_archived"] = self.request.GET.get("archived") == "1"
        ctx["filters"] = self.request.GET
        return ctx


class RadioDetailView(FleetScopedMixin, DetailView):
    template_name = "radios/detail.html"
    context_object_name = "radio"
    slug_field = "public_id"
    slug_url_kwarg = "public_id"
    active_tab = "radios"

    def get_queryset(self):
        return Radio.objects.filter(fleet=self.fleet)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["fleet"] = self.fleet
        ctx["membership"] = self.membership
        ctx["active_tab"] = self.active_tab
        ctx["current_assignment"] = self.object.current_battery_assignment()
        ctx["maintenance_events"] = self.object.maintenance_events.select_related("recorded_by")
        ctx["programming_records"] = self.object.programming_records.select_related(
            "version__configuration", "recorded_by"
        )
        ctx["current_programming_record"] = ctx["programming_records"].first()
        if self.membership.can_edit:
            ctx["battery_assign_form"] = BatteryAssignForm(fleet=self.fleet)
            ctx["maintenance_form"] = MaintenanceEventForm(fleet=self.fleet, radio=self.object)
            ctx["programming_form"] = ProgrammingRecordForm(fleet=self.fleet, radio=self.object)
        return ctx


class RadioCreateView(FleetScopedMixin, CreateView):
    require_editor = True
    template_name = "radios/form.html"
    form_class = RadioForm
    active_tab = "radios"

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
            "radios:detail",
            kwargs={"fleet_public_id": self.fleet.public_id, "public_id": self.object.public_id},
        )


class RadioUpdateView(FleetScopedMixin, UpdateView):
    require_editor = True
    template_name = "radios/form.html"
    form_class = RadioForm
    slug_field = "public_id"
    slug_url_kwarg = "public_id"
    active_tab = "radios"

    def get_queryset(self):
        return Radio.objects.filter(fleet=self.fleet)

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
            "radios:detail",
            kwargs={"fleet_public_id": self.fleet.public_id, "public_id": self.object.public_id},
        )


class RadioArchiveView(FleetScopedMixin, View):
    require_editor = True

    def post(self, request, fleet_public_id, public_id):
        radio = get_object_or_404(Radio, fleet=self.fleet, public_id=public_id)
        radio.archived_at = timezone.now()
        radio.save(update_fields=["archived_at", "updated_at"])
        messages.success(request, f"{radio.asset_label} archived.")
        return redirect("radios:list", fleet_public_id=self.fleet.public_id)


class AssignBatteryView(FleetScopedMixin, View):
    require_editor = True

    def post(self, request, fleet_public_id, public_id):
        radio = get_object_or_404(Radio, fleet=self.fleet, public_id=public_id)
        form = BatteryAssignForm(request.POST, fleet=self.fleet)
        if form.is_valid():
            try:
                assign_battery(
                    fleet=self.fleet,
                    battery=form.cleaned_data["battery"],
                    radio=radio,
                    assigned_by=request.user,
                    note=form.cleaned_data["note"],
                )
            except CrossFleetError:
                messages.error(request, "That battery isn't part of this fleet.")
            else:
                messages.success(
                    request,
                    f"{form.cleaned_data['battery'].asset_label} assigned to {radio.asset_label}.",
                )
        else:
            messages.error(request, "Couldn't assign that battery. Pick one from the list.")
        return redirect(
            "radios:detail", fleet_public_id=self.fleet.public_id, public_id=radio.public_id
        )


class UnassignBatteryView(FleetScopedMixin, View):
    require_editor = True

    def post(self, request, fleet_public_id, public_id):
        radio = get_object_or_404(Radio, fleet=self.fleet, public_id=public_id)
        assignment = radio.current_battery_assignment()
        if assignment:
            end_assignment(assignment)
            messages.success(
                request, f"{assignment.battery.asset_label} unassigned from {radio.asset_label}."
            )
        return redirect(
            "radios:detail", fleet_public_id=self.fleet.public_id, public_id=radio.public_id
        )


class MaintenanceEventCreateView(FleetScopedMixin, View):
    require_editor = True

    def post(self, request, fleet_public_id, public_id):
        radio = get_object_or_404(Radio, fleet=self.fleet, public_id=public_id)
        form = MaintenanceEventForm(request.POST, fleet=self.fleet, radio=radio)
        if form.is_valid():
            event = form.save(commit=False)
            event.recorded_by = request.user
            event.save()
            messages.success(request, "Maintenance event logged.")
        else:
            messages.error(request, "Couldn't log that maintenance event.")
        return redirect(
            "radios:detail", fleet_public_id=self.fleet.public_id, public_id=radio.public_id
        )


class BatteryListView(FleetScopedMixin, ListView):
    template_name = "batteries/list.html"
    context_object_name = "batteries"
    paginate_by = 50
    active_tab = "batteries"

    def get_queryset(self):
        qs = Battery.objects.filter(fleet=self.fleet)
        qs = qs.archived() if self.request.GET.get("archived") == "1" else qs.active()

        asset_label = self.request.GET.get("asset_label", "").strip()
        if asset_label:
            qs = qs.filter(asset_label__icontains=asset_label)

        condition = self.request.GET.get("condition", "").strip()
        if condition:
            qs = qs.filter(condition=condition)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["fleet"] = self.fleet
        ctx["membership"] = self.membership
        ctx["active_tab"] = self.active_tab
        ctx["condition_choices"] = Battery.Condition.choices
        ctx["show_archived"] = self.request.GET.get("archived") == "1"
        ctx["filters"] = self.request.GET
        return ctx


class BatteryDetailView(FleetScopedMixin, DetailView):
    template_name = "batteries/detail.html"
    context_object_name = "battery"
    slug_field = "public_id"
    slug_url_kwarg = "public_id"
    active_tab = "batteries"

    def get_queryset(self):
        return Battery.objects.filter(fleet=self.fleet)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["fleet"] = self.fleet
        ctx["membership"] = self.membership
        ctx["active_tab"] = self.active_tab
        ctx["assignments"] = self.object.assignments.select_related("radio", "assigned_by")
        return ctx


class BatteryCreateView(FleetScopedMixin, CreateView):
    require_editor = True
    template_name = "batteries/form.html"
    form_class = BatteryForm
    active_tab = "batteries"

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
            "batteries:detail",
            kwargs={"fleet_public_id": self.fleet.public_id, "public_id": self.object.public_id},
        )


class BatteryUpdateView(FleetScopedMixin, UpdateView):
    require_editor = True
    template_name = "batteries/form.html"
    form_class = BatteryForm
    slug_field = "public_id"
    slug_url_kwarg = "public_id"
    active_tab = "batteries"

    def get_queryset(self):
        return Battery.objects.filter(fleet=self.fleet)

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
            "batteries:detail",
            kwargs={"fleet_public_id": self.fleet.public_id, "public_id": self.object.public_id},
        )


class BatteryArchiveView(FleetScopedMixin, View):
    require_editor = True

    def post(self, request, fleet_public_id, public_id):
        battery = get_object_or_404(Battery, fleet=self.fleet, public_id=public_id)
        assignment = battery.current_assignment()
        if assignment:
            end_assignment(assignment)
        battery.archived_at = timezone.now()
        battery.save(update_fields=["archived_at", "updated_at"])
        messages.success(request, f"{battery.asset_label} archived.")
        return redirect("batteries:list", fleet_public_id=self.fleet.public_id)

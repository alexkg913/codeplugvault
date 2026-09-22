from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .forms import RadioForm
from .models import Radio
from .permissions import FleetScopedMixin


class RadioListView(FleetScopedMixin, ListView):
    template_name = "radios/list.html"
    context_object_name = "radios"
    paginate_by = 50

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

    def get_queryset(self):
        return Radio.objects.filter(fleet=self.fleet)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["fleet"] = self.fleet
        ctx["membership"] = self.membership
        return ctx


class RadioCreateView(FleetScopedMixin, CreateView):
    require_editor = True
    template_name = "radios/form.html"
    form_class = RadioForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["fleet"] = self.fleet
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["fleet"] = self.fleet
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

    def get_queryset(self):
        return Radio.objects.filter(fleet=self.fleet)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["fleet"] = self.fleet
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["fleet"] = self.fleet
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

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import FormView

from .forms import FleetCreateForm
from .models import Fleet, Membership
from .services import create_personal_fleet, get_active_membership


@login_required
def home(request):
    """Route a signed-in user straight to their fleet, or onboard them."""
    memberships = list(
        Membership.objects.filter(user=request.user, is_active=True).select_related("fleet")
    )
    if not memberships:
        return redirect("fleets:create")
    if len(memberships) == 1:
        return redirect("fleets:detail", public_id=memberships[0].fleet.public_id)
    return render(request, "fleets/home.html", {"memberships": memberships})


class FleetCreateView(LoginRequiredMixin, FormView):
    template_name = "fleets/create.html"
    form_class = FleetCreateForm

    def form_valid(self, form):
        fleet = create_personal_fleet(self.request.user, form.cleaned_data["name"])
        return redirect("fleets:detail", public_id=fleet.public_id)


class FleetDetailView(LoginRequiredMixin, View):
    def get(self, request, public_id):
        fleet = get_object_or_404(Fleet, public_id=public_id)
        membership = get_active_membership(request.user, fleet)
        if membership is None:
            raise Http404
        return render(request, "fleets/detail.html", {"fleet": fleet, "membership": membership})

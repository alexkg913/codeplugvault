from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404

from apps.fleets.models import Fleet, Membership
from apps.fleets.services import get_active_membership


class FleetScopedMixin(LoginRequiredMixin):
    """Resolve `self.fleet`/`self.membership` from the URL and enforce access.

    Every fleet-scoped view must mix this in. It never trusts a submitted
    `fleet_id`: the fleet always comes from the URL, and membership is looked
    up server-side on every request. Non-members get a 404 (not 403) so a
    fleet's existence isn't confirmed to people outside it. Set
    `require_editor = True` on views that mutate data.
    """

    require_editor = False

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        self.fleet = get_object_or_404(Fleet, public_id=kwargs["fleet_public_id"])
        self.membership = get_active_membership(request.user, self.fleet)
        if self.membership is None:
            raise Http404

        if self.require_editor and self.membership.role not in (
            Membership.Role.OWNER,
            Membership.Role.EDITOR,
        ):
            return HttpResponseForbidden(
                "You don't have permission to modify this fleet's records."
            )

        return super().dispatch(request, *args, **kwargs)

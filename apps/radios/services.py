"""Battery assignment rules that must hold regardless of which view calls them."""

from django.db import transaction
from django.utils import timezone

from .models import BatteryAssignment


class CrossFleetError(Exception):
    """Raised when a battery and radio don't belong to the fleet being acted on."""


@transaction.atomic
def assign_battery(*, fleet, battery, radio, assigned_by, note=""):
    """Assign `battery` to `radio`, ending whichever prior assignments overlap.

    A battery can only be attached to one radio at a time, and a radio can
    only have one active battery at a time, so this is written as a swap:
    any assignment currently active for either side is closed out first.
    """
    if battery.fleet_id != fleet.id or radio.fleet_id != fleet.id:
        raise CrossFleetError("Battery and radio must belong to the fleet being acted on.")

    BatteryAssignment.objects.filter(battery=battery, ended_at__isnull=True).update(
        ended_at=timezone.now()
    )
    BatteryAssignment.objects.filter(radio=radio, ended_at__isnull=True).update(
        ended_at=timezone.now()
    )
    return BatteryAssignment.objects.create(
        fleet=fleet, battery=battery, radio=radio, assigned_by=assigned_by, note=note
    )


def end_assignment(assignment, note=""):
    assignment.ended_at = timezone.now()
    if note:
        assignment.note = f"{assignment.note}\n{note}".strip() if assignment.note else note
    assignment.save(update_fields=["ended_at", "note"])
    return assignment

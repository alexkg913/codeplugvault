"""Fleet/membership rules that must hold regardless of which view calls them.

Centralizing these here (rather than in views/forms) keeps the tenant and
last-owner invariants enforceable from a single place, per the project brief.
"""

from django.db import transaction

from .models import Fleet, Membership


class LastOwnerError(Exception):
    """Raised when an action would leave a fleet with no active owner."""


def create_personal_fleet(user, name):
    with transaction.atomic():
        fleet = Fleet.objects.create(name=name, created_by=user)
        Membership.objects.create(fleet=fleet, user=user, role=Membership.Role.OWNER)
    return fleet


def get_active_membership(user, fleet: Fleet):
    if not getattr(user, "is_authenticated", False):
        return None
    return Membership.objects.filter(fleet=fleet, user=user, is_active=True).first()


def active_owner_count(fleet: Fleet) -> int:
    return Membership.objects.filter(
        fleet=fleet, role=Membership.Role.OWNER, is_active=True
    ).count()


@transaction.atomic
def change_membership_role(membership: Membership, new_role: str) -> Membership:
    if membership.role == Membership.Role.OWNER and new_role != Membership.Role.OWNER:
        if active_owner_count(membership.fleet) <= 1:
            raise LastOwnerError("Cannot change the role of the last active owner.")
    membership.role = new_role
    membership.save(update_fields=["role", "updated_at"])
    return membership


@transaction.atomic
def deactivate_membership(membership: Membership) -> Membership:
    if membership.role == Membership.Role.OWNER and membership.is_active:
        if active_owner_count(membership.fleet) <= 1:
            raise LastOwnerError("Cannot remove the last active owner.")
    membership.is_active = False
    membership.save(update_fields=["is_active", "updated_at"])
    return membership

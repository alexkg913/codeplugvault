import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from apps.fleets.models import Fleet, Membership
from apps.fleets.services import (
    LastOwnerError,
    change_membership_role,
    create_personal_fleet,
    deactivate_membership,
    get_active_membership,
)

User = get_user_model()

pytestmark = pytest.mark.django_db


def make_user(username="alex"):
    return User.objects.create_user(username=username, password="pw12345!")


def test_create_personal_fleet_makes_owner_membership():
    user = make_user()
    fleet = create_personal_fleet(user, "Alex's Fleet")
    membership = Membership.objects.get(fleet=fleet, user=user)
    assert membership.role == Membership.Role.OWNER
    assert membership.is_active


def test_membership_unique_per_fleet_and_user():
    user = make_user()
    fleet = Fleet.objects.create(name="Team", created_by=user)
    Membership.objects.create(fleet=fleet, user=user, role=Membership.Role.OWNER)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Membership.objects.create(fleet=fleet, user=user, role=Membership.Role.VIEWER)


def test_cannot_demote_last_active_owner():
    user = make_user()
    fleet = create_personal_fleet(user, "Solo Fleet")
    membership = Membership.objects.get(fleet=fleet, user=user)
    with pytest.raises(LastOwnerError):
        change_membership_role(membership, Membership.Role.EDITOR)


def test_cannot_deactivate_last_active_owner():
    user = make_user()
    fleet = create_personal_fleet(user, "Solo Fleet")
    membership = Membership.objects.get(fleet=fleet, user=user)
    with pytest.raises(LastOwnerError):
        deactivate_membership(membership)


def test_second_owner_allows_demoting_first():
    owner = make_user("owner")
    other = make_user("other")
    fleet = create_personal_fleet(owner, "Team Fleet")
    Membership.objects.create(fleet=fleet, user=other, role=Membership.Role.OWNER)

    owner_membership = Membership.objects.get(fleet=fleet, user=owner)
    change_membership_role(owner_membership, Membership.Role.EDITOR)
    owner_membership.refresh_from_db()
    assert owner_membership.role == Membership.Role.EDITOR


def test_get_active_membership_returns_none_for_non_member():
    owner = make_user("owner")
    stranger = make_user("stranger")
    fleet = create_personal_fleet(owner, "Team Fleet")
    assert get_active_membership(stranger, fleet) is None


def test_get_active_membership_returns_none_for_anonymous():
    from django.contrib.auth.models import AnonymousUser

    owner = make_user("owner")
    fleet = create_personal_fleet(owner, "Team Fleet")
    assert get_active_membership(AnonymousUser(), fleet) is None

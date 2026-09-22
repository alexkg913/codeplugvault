import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.fleets.services import create_personal_fleet
from apps.radios.models import Radio

User = get_user_model()

pytestmark = pytest.mark.django_db


def make_fleet(name="Fleet"):
    user = User.objects.create_user(username=f"user-{name}", password="pw12345!")
    return create_personal_fleet(user, name)


def make_radio(fleet, asset_label="R-1", **kwargs):
    return Radio.objects.create(fleet=fleet, asset_label=asset_label, **kwargs)


def test_duplicate_asset_label_rejected_within_fleet():
    fleet = make_fleet("Fleet A")
    make_radio(fleet, "R-1")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            make_radio(fleet, "R-1")


def test_same_asset_label_allowed_across_fleets():
    fleet_a = make_fleet("Fleet A")
    fleet_b = make_fleet("Fleet B")
    make_radio(fleet_a, "R-1")
    make_radio(fleet_b, "R-1")  # should not raise
    assert Radio.objects.filter(asset_label="R-1").count() == 2


def test_active_and_archived_querysets():
    fleet = make_fleet("Fleet A")
    make_radio(fleet, "R-1")
    make_radio(fleet, "R-2", archived_at=timezone.now())

    active_labels = list(
        Radio.objects.filter(fleet=fleet).active().values_list("asset_label", flat=True)
    )
    archived_labels = list(
        Radio.objects.filter(fleet=fleet).archived().values_list("asset_label", flat=True)
    )
    assert active_labels == ["R-1"]
    assert archived_labels == ["R-2"]

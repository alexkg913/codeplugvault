import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.fleets.services import create_personal_fleet
from apps.radios.models import Battery, BatteryAssignment, MaintenanceEvent, Radio
from apps.radios.services import CrossFleetError, assign_battery, end_assignment

User = get_user_model()

pytestmark = pytest.mark.django_db


def make_fleet(name="Fleet"):
    user = User.objects.create_user(username=f"user-{name}", password="pw12345!")
    return create_personal_fleet(user, name)


def test_duplicate_battery_asset_label_rejected_within_fleet():
    fleet = make_fleet("Fleet A")
    Battery.objects.create(fleet=fleet, asset_label="BAT-1")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Battery.objects.create(fleet=fleet, asset_label="BAT-1")


def test_assign_battery_creates_active_assignment():
    fleet = make_fleet("Fleet A")
    owner = fleet.created_by
    radio = Radio.objects.create(fleet=fleet, asset_label="R-1")
    battery = Battery.objects.create(fleet=fleet, asset_label="BAT-1")

    assignment = assign_battery(fleet=fleet, battery=battery, radio=radio, assigned_by=owner)
    assert assignment.ended_at is None
    assert radio.current_battery_assignment() == assignment
    assert battery.current_assignment() == assignment


def test_assigning_battery_to_new_radio_ends_prior_assignment_and_keeps_history():
    fleet = make_fleet("Fleet A")
    owner = fleet.created_by
    radio1 = Radio.objects.create(fleet=fleet, asset_label="R-1")
    radio2 = Radio.objects.create(fleet=fleet, asset_label="R-2")
    battery = Battery.objects.create(fleet=fleet, asset_label="BAT-1")

    first = assign_battery(fleet=fleet, battery=battery, radio=radio1, assigned_by=owner)
    second = assign_battery(fleet=fleet, battery=battery, radio=radio2, assigned_by=owner)

    first.refresh_from_db()
    assert first.ended_at is not None
    assert second.ended_at is None
    assert battery.assignments.count() == 2
    assert radio1.current_battery_assignment() is None
    assert radio2.current_battery_assignment() == second


def test_assigning_new_battery_to_radio_ends_radios_prior_assignment():
    fleet = make_fleet("Fleet A")
    owner = fleet.created_by
    radio = Radio.objects.create(fleet=fleet, asset_label="R-1")
    battery1 = Battery.objects.create(fleet=fleet, asset_label="BAT-1")
    battery2 = Battery.objects.create(fleet=fleet, asset_label="BAT-2")

    first = assign_battery(fleet=fleet, battery=battery1, radio=radio, assigned_by=owner)
    second = assign_battery(fleet=fleet, battery=battery2, radio=radio, assigned_by=owner)

    first.refresh_from_db()
    assert first.ended_at is not None
    assert radio.current_battery_assignment() == second


def test_battery_cannot_be_active_on_two_radios_at_the_database_level():
    fleet = make_fleet("Fleet A")
    owner = fleet.created_by
    radio1 = Radio.objects.create(fleet=fleet, asset_label="R-1")
    radio2 = Radio.objects.create(fleet=fleet, asset_label="R-2")
    battery = Battery.objects.create(fleet=fleet, asset_label="BAT-1")
    BatteryAssignment.objects.create(fleet=fleet, battery=battery, radio=radio1, assigned_by=owner)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            BatteryAssignment.objects.create(
                fleet=fleet, battery=battery, radio=radio2, assigned_by=owner
            )


def test_radio_cannot_have_two_active_batteries_at_the_database_level():
    fleet = make_fleet("Fleet A")
    owner = fleet.created_by
    radio = Radio.objects.create(fleet=fleet, asset_label="R-1")
    battery1 = Battery.objects.create(fleet=fleet, asset_label="BAT-1")
    battery2 = Battery.objects.create(fleet=fleet, asset_label="BAT-2")
    BatteryAssignment.objects.create(fleet=fleet, battery=battery1, radio=radio, assigned_by=owner)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            BatteryAssignment.objects.create(
                fleet=fleet, battery=battery2, radio=radio, assigned_by=owner
            )


def test_assign_battery_rejects_cross_fleet_pairing():
    fleet_a = make_fleet("Fleet A")
    fleet_b = make_fleet("Fleet B")
    owner = fleet_a.created_by
    radio = Radio.objects.create(fleet=fleet_a, asset_label="R-1")
    battery = Battery.objects.create(fleet=fleet_b, asset_label="BAT-1")

    with pytest.raises(CrossFleetError):
        assign_battery(fleet=fleet_a, battery=battery, radio=radio, assigned_by=owner)


def test_end_assignment_sets_ended_at():
    fleet = make_fleet("Fleet A")
    owner = fleet.created_by
    radio = Radio.objects.create(fleet=fleet, asset_label="R-1")
    battery = Battery.objects.create(fleet=fleet, asset_label="BAT-1")
    assignment = assign_battery(fleet=fleet, battery=battery, radio=radio, assigned_by=owner)

    end_assignment(assignment)
    assignment.refresh_from_db()
    assert assignment.ended_at is not None


def test_maintenance_events_ordered_most_recent_first():
    fleet = make_fleet("Fleet A")
    owner = fleet.created_by
    radio = Radio.objects.create(fleet=fleet, asset_label="R-1")
    MaintenanceEvent.objects.create(
        fleet=fleet,
        radio=radio,
        kind="inspection",
        occurred_at=timezone.datetime(2026, 1, 1).date(),
        recorded_by=owner,
    )
    MaintenanceEvent.objects.create(
        fleet=fleet,
        radio=radio,
        kind="repair",
        occurred_at=timezone.datetime(2026, 6, 1).date(),
        recorded_by=owner,
    )
    events = list(radio.maintenance_events.all())
    assert [e.kind for e in events] == ["repair", "inspection"]

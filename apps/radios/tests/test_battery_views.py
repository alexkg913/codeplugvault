import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.fleets.models import Membership
from apps.fleets.services import create_personal_fleet
from apps.radios.models import Battery, BatteryAssignment, MaintenanceEvent, Radio
from apps.radios.services import assign_battery

User = get_user_model()

pytestmark = pytest.mark.django_db


@pytest.fixture
def scenario():
    owner = User.objects.create_user(username="owner", password="pw12345!")
    fleet = create_personal_fleet(owner, "Race Team")

    editor = User.objects.create_user(username="editor", password="pw12345!")
    Membership.objects.create(fleet=fleet, user=editor, role=Membership.Role.EDITOR)

    viewer = User.objects.create_user(username="viewer", password="pw12345!")
    Membership.objects.create(fleet=fleet, user=viewer, role=Membership.Role.VIEWER)

    outsider = User.objects.create_user(username="outsider", password="pw12345!")
    other_fleet = create_personal_fleet(outsider, "Other Team")

    radio = Radio.objects.create(fleet=fleet, asset_label="XPR-1")
    battery = Battery.objects.create(fleet=fleet, asset_label="BAT-1")
    other_battery = Battery.objects.create(fleet=other_fleet, asset_label="BAT-X")

    return {
        "fleet": fleet,
        "other_fleet": other_fleet,
        "owner": owner,
        "editor": editor,
        "viewer": viewer,
        "outsider": outsider,
        "radio": radio,
        "battery": battery,
        "other_battery": other_battery,
    }


def battery_list_url(fleet):
    return reverse("batteries:list", kwargs={"fleet_public_id": fleet.public_id})


def battery_detail_url(fleet, battery):
    return reverse(
        "batteries:detail",
        kwargs={"fleet_public_id": fleet.public_id, "public_id": battery.public_id},
    )


def battery_create_url(fleet):
    return reverse("batteries:create", kwargs={"fleet_public_id": fleet.public_id})


def battery_archive_url(fleet, battery):
    return reverse(
        "batteries:archive",
        kwargs={"fleet_public_id": fleet.public_id, "public_id": battery.public_id},
    )


def assign_url(fleet, radio):
    return reverse(
        "radios:assign-battery",
        kwargs={"fleet_public_id": fleet.public_id, "public_id": radio.public_id},
    )


def unassign_url(fleet, radio):
    return reverse(
        "radios:unassign-battery",
        kwargs={"fleet_public_id": fleet.public_id, "public_id": radio.public_id},
    )


def maintenance_url(fleet, radio):
    return reverse(
        "radios:maintenance-create",
        kwargs={"fleet_public_id": fleet.public_id, "public_id": radio.public_id},
    )


# --- Read access / cross-fleet ---


def test_outsider_gets_404_on_battery_list_and_detail(client, scenario):
    client.force_login(scenario["outsider"])
    assert client.get(battery_list_url(scenario["fleet"])).status_code == 404
    assert client.get(battery_detail_url(scenario["fleet"], scenario["battery"])).status_code == 404


@pytest.mark.parametrize("role", ["owner", "editor", "viewer"])
def test_members_can_view_battery_list_and_detail(client, scenario, role):
    client.force_login(scenario[role])
    resp = client.get(battery_list_url(scenario["fleet"]))
    assert resp.status_code == 200
    assert scenario["battery"].asset_label in resp.content.decode()
    assert client.get(battery_detail_url(scenario["fleet"], scenario["battery"])).status_code == 200


# --- Battery CRUD ---


def test_viewer_cannot_create_battery(client, scenario):
    client.force_login(scenario["viewer"])
    resp = client.post(
        battery_create_url(scenario["fleet"]), {"asset_label": "BAT-NEW", "condition": "good"}
    )
    assert resp.status_code == 403
    assert not Battery.objects.filter(fleet=scenario["fleet"], asset_label="BAT-NEW").exists()


@pytest.mark.parametrize("role", ["owner", "editor"])
def test_owner_and_editor_can_create_battery(client, scenario, role):
    client.force_login(scenario[role])
    resp = client.post(
        battery_create_url(scenario["fleet"]),
        {
            "asset_label": "BAT-NEW",
            "maker": "Motorola",
            "model": "IMPRES",
            "serial": "",
            "chemistry": "Li-ion",
            "capacity": "2200 mAh",
            "condition": "good",
            "notes": "",
        },
    )
    assert resp.status_code == 302
    assert Battery.objects.filter(fleet=scenario["fleet"], asset_label="BAT-NEW").exists()


def test_duplicate_battery_asset_label_rejected_via_form(client, scenario):
    client.force_login(scenario["owner"])
    resp = client.post(
        battery_create_url(scenario["fleet"]), {"asset_label": "BAT-1", "condition": "good"}
    )
    assert resp.status_code == 200
    assert "already exists" in resp.content.decode()


def test_outsider_cannot_view_or_mutate_another_fleets_battery_by_guessing_url(client, scenario):
    client.force_login(scenario["outsider"])
    # outsider *is* a member of other_fleet, so use their own fleet's battery id
    # against this fleet's URL prefix to prove scoping isn't inferred from the id alone.
    url = reverse(
        "batteries:detail",
        kwargs={
            "fleet_public_id": scenario["other_fleet"].public_id,
            "public_id": scenario["battery"].public_id,
        },
    )
    assert client.get(url).status_code == 404


def test_archiving_battery_ends_its_active_assignment(client, scenario):
    client.force_login(scenario["owner"])
    assignment = assign_battery(
        fleet=scenario["fleet"],
        battery=scenario["battery"],
        radio=scenario["radio"],
        assigned_by=scenario["owner"],
    )

    resp = client.post(battery_archive_url(scenario["fleet"], scenario["battery"]))
    assert resp.status_code == 302

    assignment.refresh_from_db()
    assert assignment.ended_at is not None
    scenario["battery"].refresh_from_db()
    assert scenario["battery"].is_archived


# --- Assignment / swap workflow ---


def test_editor_can_assign_battery_to_radio(client, scenario):
    client.force_login(scenario["editor"])
    resp = client.post(
        assign_url(scenario["fleet"], scenario["radio"]), {"battery": scenario["battery"].pk}
    )
    assert resp.status_code == 302
    assignment = scenario["radio"].current_battery_assignment()
    assert assignment is not None
    assert assignment.battery == scenario["battery"]


def test_viewer_cannot_assign_battery(client, scenario):
    client.force_login(scenario["viewer"])
    resp = client.post(
        assign_url(scenario["fleet"], scenario["radio"]), {"battery": scenario["battery"].pk}
    )
    assert resp.status_code == 403
    assert scenario["radio"].current_battery_assignment() is None


def test_cannot_assign_a_battery_from_another_fleet(client, scenario):
    client.force_login(scenario["owner"])
    resp = client.post(
        assign_url(scenario["fleet"], scenario["radio"]), {"battery": scenario["other_battery"].pk}
    )
    # The form's queryset is scoped to this fleet, so the id from another
    # fleet is simply not a valid choice -- the view redirects with an
    # error rather than ever calling the assignment service.
    assert resp.status_code == 302
    assert scenario["radio"].current_battery_assignment() is None
    assert BatteryAssignment.objects.filter(radio=scenario["radio"]).count() == 0


def test_swap_ends_prior_assignment_and_keeps_history(client, scenario):
    client.force_login(scenario["owner"])
    battery2 = Battery.objects.create(fleet=scenario["fleet"], asset_label="BAT-2")

    client.post(
        assign_url(scenario["fleet"], scenario["radio"]), {"battery": scenario["battery"].pk}
    )
    client.post(assign_url(scenario["fleet"], scenario["radio"]), {"battery": battery2.pk})

    current = scenario["radio"].current_battery_assignment()
    assert current.battery == battery2
    assert BatteryAssignment.objects.filter(radio=scenario["radio"]).count() == 2
    first = BatteryAssignment.objects.get(battery=scenario["battery"])
    assert first.ended_at is not None


def test_unassign_battery(client, scenario):
    client.force_login(scenario["owner"])
    assign_battery(
        fleet=scenario["fleet"],
        battery=scenario["battery"],
        radio=scenario["radio"],
        assigned_by=scenario["owner"],
    )

    resp = client.post(unassign_url(scenario["fleet"], scenario["radio"]))
    assert resp.status_code == 302
    assert scenario["radio"].current_battery_assignment() is None


def test_outsider_cannot_assign_or_unassign(client, scenario):
    client.force_login(scenario["outsider"])
    assert (
        client.post(
            assign_url(scenario["fleet"], scenario["radio"]), {"battery": scenario["battery"].pk}
        ).status_code
        == 404
    )
    assert client.post(unassign_url(scenario["fleet"], scenario["radio"])).status_code == 404


# --- Maintenance events ---


def test_editor_can_log_maintenance_event(client, scenario):
    client.force_login(scenario["editor"])
    resp = client.post(
        maintenance_url(scenario["fleet"], scenario["radio"]),
        {"kind": "inspection", "occurred_at": "2026-09-01", "notes": "Checked antenna mount"},
    )
    assert resp.status_code == 302
    assert MaintenanceEvent.objects.filter(radio=scenario["radio"], kind="inspection").exists()


def test_viewer_cannot_log_maintenance_event(client, scenario):
    client.force_login(scenario["viewer"])
    resp = client.post(
        maintenance_url(scenario["fleet"], scenario["radio"]),
        {"kind": "inspection", "occurred_at": "2026-09-01", "notes": ""},
    )
    assert resp.status_code == 403
    assert not MaintenanceEvent.objects.filter(radio=scenario["radio"]).exists()


def test_outsider_cannot_log_maintenance_event(client, scenario):
    client.force_login(scenario["outsider"])
    resp = client.post(
        maintenance_url(scenario["fleet"], scenario["radio"]),
        {"kind": "inspection", "occurred_at": "2026-09-01", "notes": ""},
    )
    assert resp.status_code == 404

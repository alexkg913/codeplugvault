import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.fleets.models import Membership
from apps.fleets.services import create_personal_fleet
from apps.radios.models import Radio

User = get_user_model()

pytestmark = pytest.mark.django_db


@pytest.fixture
def fleet_and_users():
    owner = User.objects.create_user(username="owner", password="pw12345!")
    fleet = create_personal_fleet(owner, "Race Team")

    editor = User.objects.create_user(username="editor", password="pw12345!")
    Membership.objects.create(fleet=fleet, user=editor, role=Membership.Role.EDITOR)

    viewer = User.objects.create_user(username="viewer", password="pw12345!")
    Membership.objects.create(fleet=fleet, user=viewer, role=Membership.Role.VIEWER)

    outsider = User.objects.create_user(username="outsider", password="pw12345!")
    other_fleet = create_personal_fleet(outsider, "Other Team")

    radio = Radio.objects.create(fleet=fleet, asset_label="XPR-1")

    return {
        "fleet": fleet,
        "other_fleet": other_fleet,
        "owner": owner,
        "editor": editor,
        "viewer": viewer,
        "outsider": outsider,
        "radio": radio,
    }


def list_url(fleet):
    return reverse("radios:list", kwargs={"fleet_public_id": fleet.public_id})


def detail_url(fleet, radio):
    return reverse(
        "radios:detail", kwargs={"fleet_public_id": fleet.public_id, "public_id": radio.public_id}
    )


def create_url(fleet):
    return reverse("radios:create", kwargs={"fleet_public_id": fleet.public_id})


def edit_url(fleet, radio):
    return reverse(
        "radios:edit", kwargs={"fleet_public_id": fleet.public_id, "public_id": radio.public_id}
    )


def archive_url(fleet, radio):
    return reverse(
        "radios:archive", kwargs={"fleet_public_id": fleet.public_id, "public_id": radio.public_id}
    )


# --- Read access ---


def test_anonymous_is_redirected_to_login(client, fleet_and_users):
    resp = client.get(list_url(fleet_and_users["fleet"]))
    assert resp.status_code == 302
    assert "/accounts/login/" in resp.url


@pytest.mark.parametrize("role", ["owner", "editor", "viewer"])
def test_members_can_view_list_and_detail(client, fleet_and_users, role):
    client.force_login(fleet_and_users[role])
    fleet = fleet_and_users["fleet"]
    radio = fleet_and_users["radio"]

    resp = client.get(list_url(fleet))
    assert resp.status_code == 200
    assert radio.asset_label in resp.content.decode()

    resp = client.get(detail_url(fleet, radio))
    assert resp.status_code == 200


def test_outsider_gets_404_on_list_and_detail(client, fleet_and_users):
    client.force_login(fleet_and_users["outsider"])
    fleet = fleet_and_users["fleet"]
    radio = fleet_and_users["radio"]

    assert client.get(list_url(fleet)).status_code == 404
    assert client.get(detail_url(fleet, radio)).status_code == 404


def test_member_of_another_fleet_guessing_radio_url_gets_404(client, fleet_and_users):
    # Outsider is a member of other_fleet, but the radio belongs to `fleet`.
    client.force_login(fleet_and_users["outsider"])
    other_fleet = fleet_and_users["other_fleet"]
    radio = fleet_and_users["radio"]
    url = reverse(
        "radios:detail",
        kwargs={"fleet_public_id": other_fleet.public_id, "public_id": radio.public_id},
    )
    assert client.get(url).status_code == 404


# --- Mutations ---


@pytest.mark.parametrize("role", ["owner", "editor"])
def test_owner_and_editor_can_create_radio(client, fleet_and_users, role):
    client.force_login(fleet_and_users[role])
    fleet = fleet_and_users["fleet"]
    resp = client.post(
        create_url(fleet),
        {
            "asset_label": "XPR-NEW",
            "manufacturer": "Motorola",
            "model": "XPR7550e",
            "serial": "",
            "radio_id": "",
            "band": "UHF",
            "firmware": "",
            "purpose": "spotter",
            "status": "active",
            "notes": "",
        },
    )
    assert resp.status_code == 302
    assert Radio.objects.filter(fleet=fleet, asset_label="XPR-NEW").exists()


def test_viewer_cannot_create_radio(client, fleet_and_users):
    client.force_login(fleet_and_users["viewer"])
    fleet = fleet_and_users["fleet"]
    resp = client.post(create_url(fleet), {"asset_label": "XPR-NEW", "status": "active"})
    assert resp.status_code == 403
    assert not Radio.objects.filter(fleet=fleet, asset_label="XPR-NEW").exists()


def test_viewer_cannot_edit_radio(client, fleet_and_users):
    client.force_login(fleet_and_users["viewer"])
    fleet = fleet_and_users["fleet"]
    radio = fleet_and_users["radio"]
    resp = client.post(edit_url(fleet, radio), {"asset_label": "CHANGED", "status": "active"})
    assert resp.status_code == 403
    radio.refresh_from_db()
    assert radio.asset_label != "CHANGED"


def test_viewer_cannot_archive_radio(client, fleet_and_users):
    client.force_login(fleet_and_users["viewer"])
    fleet = fleet_and_users["fleet"]
    radio = fleet_and_users["radio"]
    resp = client.post(archive_url(fleet, radio))
    assert resp.status_code == 403
    radio.refresh_from_db()
    assert radio.archived_at is None


def test_outsider_cannot_create_edit_or_archive(client, fleet_and_users):
    client.force_login(fleet_and_users["outsider"])
    fleet = fleet_and_users["fleet"]
    radio = fleet_and_users["radio"]

    assert (
        client.post(create_url(fleet), {"asset_label": "X", "status": "active"}).status_code == 404
    )
    assert (
        client.post(edit_url(fleet, radio), {"asset_label": "X", "status": "active"}).status_code
        == 404
    )
    assert client.post(archive_url(fleet, radio)).status_code == 404


def test_editor_can_archive_and_it_leaves_default_list(client, fleet_and_users):
    client.force_login(fleet_and_users["editor"])
    fleet = fleet_and_users["fleet"]
    radio = fleet_and_users["radio"]

    resp = client.post(archive_url(fleet, radio))
    assert resp.status_code == 302
    radio.refresh_from_db()
    assert radio.archived_at is not None

    # Check for the radio's own link rather than its asset label text: the
    # post-archive flash message ("XPR-1 archived.") also contains the label.
    radio_link = detail_url(fleet, radio)

    resp = client.get(list_url(fleet))
    assert radio_link not in resp.content.decode()

    resp = client.get(list_url(fleet) + "?archived=1")
    assert radio_link in resp.content.decode()

    resp = client.get(detail_url(fleet, radio))
    assert resp.status_code == 200


def test_duplicate_asset_label_rejected_via_form(client, fleet_and_users):
    client.force_login(fleet_and_users["owner"])
    fleet = fleet_and_users["fleet"]
    resp = client.post(create_url(fleet), {"asset_label": "XPR-1", "status": "active"})
    assert resp.status_code == 200  # re-renders the form with an error
    assert "already exists" in resp.content.decode()

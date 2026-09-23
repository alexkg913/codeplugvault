import hashlib

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.configurations.models import (
    ChannelSnapshot,
    Configuration,
    ConfigurationVersion,
    VersionAttachment,
)
from apps.configurations.services import create_version, get_attachment_storage, publish_version
from apps.fleets.models import Membership
from apps.fleets.services import create_personal_fleet
from apps.radios.models import Radio

User = get_user_model()

pytestmark = pytest.mark.django_db


@pytest.fixture
def scenario(tmp_path, settings):
    settings.PRIVATE_MEDIA_ROOT = tmp_path

    owner = User.objects.create_user(username="owner", password="pw12345!")
    fleet = create_personal_fleet(owner, "Race Team")

    editor = User.objects.create_user(username="editor", password="pw12345!")
    Membership.objects.create(fleet=fleet, user=editor, role=Membership.Role.EDITOR)

    viewer = User.objects.create_user(username="viewer", password="pw12345!")
    Membership.objects.create(fleet=fleet, user=viewer, role=Membership.Role.VIEWER)

    outsider = User.objects.create_user(username="outsider", password="pw12345!")
    other_fleet = create_personal_fleet(outsider, "Other Team")

    radio = Radio.objects.create(fleet=fleet, asset_label="XPR-1")
    configuration = Configuration.objects.create(fleet=fleet, name="Race Weekend", created_by=owner)
    draft_version = create_version(configuration=configuration, created_by=owner)
    published_version = create_version(configuration=configuration, created_by=owner)
    publish_version(published_version)

    return {
        "fleet": fleet,
        "other_fleet": other_fleet,
        "owner": owner,
        "editor": editor,
        "viewer": viewer,
        "outsider": outsider,
        "radio": radio,
        "configuration": configuration,
        "draft_version": draft_version,
        "published_version": published_version,
        "storage_dir": tmp_path,
    }


def config_list_url(fleet):
    return reverse("configurations:list", kwargs={"fleet_public_id": fleet.public_id})


def config_detail_url(fleet, configuration):
    return reverse(
        "configurations:detail",
        kwargs={"fleet_public_id": fleet.public_id, "public_id": configuration.public_id},
    )


def config_create_url(fleet):
    return reverse("configurations:create", kwargs={"fleet_public_id": fleet.public_id})


def version_create_url(fleet, configuration):
    return reverse(
        "configurations:version-create",
        kwargs={"fleet_public_id": fleet.public_id, "public_id": configuration.public_id},
    )


def version_detail_url(fleet, version):
    return reverse(
        "configurations:version-detail",
        kwargs={"fleet_public_id": fleet.public_id, "public_id": version.public_id},
    )


def version_publish_url(fleet, version):
    return reverse(
        "configurations:version-publish",
        kwargs={"fleet_public_id": fleet.public_id, "public_id": version.public_id},
    )


def channel_create_url(fleet, version):
    return reverse(
        "configurations:channel-create",
        kwargs={"fleet_public_id": fleet.public_id, "public_id": version.public_id},
    )


def channel_edit_url(fleet, version, channel):
    return reverse(
        "configurations:channel-edit",
        kwargs={
            "fleet_public_id": fleet.public_id,
            "public_id": version.public_id,
            "channel_id": channel.pk,
        },
    )


def channel_delete_url(fleet, version, channel):
    return reverse(
        "configurations:channel-delete",
        kwargs={
            "fleet_public_id": fleet.public_id,
            "public_id": version.public_id,
            "channel_id": channel.pk,
        },
    )


def attachment_upload_url(fleet, version):
    return reverse(
        "configurations:attachment-upload",
        kwargs={"fleet_public_id": fleet.public_id, "public_id": version.public_id},
    )


def attachment_download_url(fleet, version, attachment):
    return reverse(
        "configurations:attachment-download",
        kwargs={
            "fleet_public_id": fleet.public_id,
            "public_id": version.public_id,
            "attachment_id": attachment.pk,
        },
    )


def programming_create_url(fleet, radio):
    return reverse(
        "programming-create",
        kwargs={"fleet_public_id": fleet.public_id, "public_id": radio.public_id},
    )


# --- Configuration CRUD ---


def test_outsider_gets_404_on_configuration_list_and_detail(client, scenario):
    client.force_login(scenario["outsider"])
    assert client.get(config_list_url(scenario["fleet"])).status_code == 404
    assert (
        client.get(config_detail_url(scenario["fleet"], scenario["configuration"])).status_code
        == 404
    )


@pytest.mark.parametrize("role", ["owner", "editor", "viewer"])
def test_members_can_view_configuration_list_and_detail(client, scenario, role):
    client.force_login(scenario[role])
    resp = client.get(config_list_url(scenario["fleet"]))
    assert resp.status_code == 200
    assert scenario["configuration"].name in resp.content.decode()
    assert (
        client.get(config_detail_url(scenario["fleet"], scenario["configuration"])).status_code
        == 200
    )


def test_viewer_cannot_create_configuration(client, scenario):
    client.force_login(scenario["viewer"])
    resp = client.post(config_create_url(scenario["fleet"]), {"name": "New Config"})
    assert resp.status_code == 403
    assert not Configuration.objects.filter(fleet=scenario["fleet"], name="New Config").exists()


@pytest.mark.parametrize("role", ["owner", "editor"])
def test_owner_and_editor_can_create_configuration(client, scenario, role):
    client.force_login(scenario[role])
    resp = client.post(config_create_url(scenario["fleet"]), {"name": "New Config"})
    assert resp.status_code == 302
    assert Configuration.objects.filter(fleet=scenario["fleet"], name="New Config").exists()


def test_duplicate_configuration_name_rejected_via_form(client, scenario):
    client.force_login(scenario["owner"])
    resp = client.post(config_create_url(scenario["fleet"]), {"name": "Race Weekend"})
    assert resp.status_code == 200
    assert "already exists" in resp.content.decode()


# --- Version create / publish / draft immutability ---


def test_viewer_cannot_create_version(client, scenario):
    client.force_login(scenario["viewer"])
    resp = client.post(
        version_create_url(scenario["fleet"], scenario["configuration"]), {"label": "x"}
    )
    assert resp.status_code == 403


def test_editor_can_create_version_as_draft(client, scenario):
    client.force_login(scenario["editor"])
    resp = client.post(
        version_create_url(scenario["fleet"], scenario["configuration"]),
        {"label": "Sprint spec", "release_notes": ""},
    )
    assert resp.status_code == 302
    version = ConfigurationVersion.objects.get(
        configuration=scenario["configuration"], label="Sprint spec"
    )
    assert version.is_draft
    assert version.version_number == 3  # two versions already exist in the fixture


def test_viewer_cannot_publish_version(client, scenario):
    client.force_login(scenario["viewer"])
    resp = client.post(version_publish_url(scenario["fleet"], scenario["draft_version"]))
    assert resp.status_code == 403
    scenario["draft_version"].refresh_from_db()
    assert scenario["draft_version"].is_draft


def test_editor_can_publish_draft_version(client, scenario):
    client.force_login(scenario["editor"])
    resp = client.post(version_publish_url(scenario["fleet"], scenario["draft_version"]))
    assert resp.status_code == 302
    scenario["draft_version"].refresh_from_db()
    assert scenario["draft_version"].is_published


def test_publishing_an_already_published_version_does_not_crash(client, scenario):
    client.force_login(scenario["owner"])
    resp = client.post(version_publish_url(scenario["fleet"], scenario["published_version"]))
    assert resp.status_code == 302  # redirects with an error message, no 500


# --- Channel CRUD + draft-only guard ---


def test_editor_can_add_channel_to_draft_version(client, scenario):
    client.force_login(scenario["editor"])
    resp = client.post(
        channel_create_url(scenario["fleet"], scenario["draft_version"]),
        {"position": 1, "zone": "Pit", "name": "Alpha", "mode": "analog"},
    )
    assert resp.status_code == 302
    assert ChannelSnapshot.objects.filter(version=scenario["draft_version"], position=1).exists()


def test_duplicate_channel_position_rejected(client, scenario):
    client.force_login(scenario["owner"])
    ChannelSnapshot.objects.create(
        fleet=scenario["fleet"],
        version=scenario["draft_version"],
        position=1,
        name="Alpha",
        mode="analog",
    )
    resp = client.post(
        channel_create_url(scenario["fleet"], scenario["draft_version"]),
        {"position": 1, "name": "Bravo", "mode": "analog"},
    )
    assert resp.status_code == 200
    assert "already occupies" in resp.content.decode()


def test_digital_channel_requires_color_code(client, scenario):
    client.force_login(scenario["owner"])
    resp = client.post(
        channel_create_url(scenario["fleet"], scenario["draft_version"]),
        {"position": 1, "name": "Digi", "mode": "digital"},
    )
    assert resp.status_code == 200
    assert "Color code is required" in resp.content.decode()


def test_editor_cannot_add_channel_to_published_version(client, scenario):
    client.force_login(scenario["editor"])
    resp = client.post(
        channel_create_url(scenario["fleet"], scenario["published_version"]),
        {"position": 1, "name": "Alpha", "mode": "analog"},
    )
    assert resp.status_code == 302
    assert not ChannelSnapshot.objects.filter(version=scenario["published_version"]).exists()


def test_editor_can_edit_and_delete_channel_on_draft_version(client, scenario):
    client.force_login(scenario["editor"])
    channel = ChannelSnapshot.objects.create(
        fleet=scenario["fleet"],
        version=scenario["draft_version"],
        position=1,
        name="Alpha",
        mode="analog",
    )

    resp = client.post(
        channel_edit_url(scenario["fleet"], scenario["draft_version"], channel),
        {"position": 1, "name": "Alpha Prime", "mode": "analog"},
    )
    assert resp.status_code == 302
    channel.refresh_from_db()
    assert channel.name == "Alpha Prime"

    resp = client.post(channel_delete_url(scenario["fleet"], scenario["draft_version"], channel))
    assert resp.status_code == 302
    assert not ChannelSnapshot.objects.filter(pk=channel.pk).exists()


def test_editor_cannot_edit_or_delete_channel_on_published_version(client, scenario):
    client.force_login(scenario["editor"])
    channel = ChannelSnapshot.objects.create(
        fleet=scenario["fleet"],
        version=scenario["published_version"],
        position=1,
        name="Alpha",
        mode="analog",
    )

    client.post(
        channel_edit_url(scenario["fleet"], scenario["published_version"], channel),
        {"position": 1, "name": "Changed", "mode": "analog"},
    )
    channel.refresh_from_db()
    assert channel.name == "Alpha"

    client.post(channel_delete_url(scenario["fleet"], scenario["published_version"], channel))
    assert ChannelSnapshot.objects.filter(pk=channel.pk).exists()


def test_viewer_cannot_add_channel(client, scenario):
    client.force_login(scenario["viewer"])
    resp = client.post(
        channel_create_url(scenario["fleet"], scenario["draft_version"]),
        {"position": 1, "name": "Alpha", "mode": "analog"},
    )
    assert resp.status_code == 403


# --- Attachments ---


def test_editor_can_upload_and_download_attachment_with_correct_hash(client, scenario):
    client.force_login(scenario["editor"])
    content = b"fake codeplug bytes " * 100
    upload = SimpleUploadedFile("codeplug.ctb", content, content_type="application/octet-stream")

    resp = client.post(
        attachment_upload_url(scenario["fleet"], scenario["draft_version"]), {"file": upload}
    )
    assert resp.status_code == 302

    attachment = VersionAttachment.objects.get(version=scenario["draft_version"])
    assert attachment.original_filename == "codeplug.ctb"
    assert attachment.byte_size == len(content)
    assert attachment.sha256 == hashlib.sha256(content).hexdigest()

    resp = client.get(
        attachment_download_url(scenario["fleet"], scenario["draft_version"], attachment)
    )
    assert resp.status_code == 200
    assert b"".join(resp.streaming_content) == content
    assert "codeplug.ctb" in resp["Content-Disposition"]


def test_upload_accepts_xctb_extension(client, scenario):
    client.force_login(scenario["editor"])
    upload = SimpleUploadedFile(
        "codeplug.xctb", b"newer motorola cps export", content_type="application/octet-stream"
    )
    resp = client.post(
        attachment_upload_url(scenario["fleet"], scenario["draft_version"]), {"file": upload}
    )
    assert resp.status_code == 302
    assert VersionAttachment.objects.filter(
        version=scenario["draft_version"], original_filename="codeplug.xctb"
    ).exists()


def test_upload_rejects_disallowed_extension(client, scenario):
    client.force_login(scenario["owner"])
    upload = SimpleUploadedFile("virus.exe", b"x", content_type="application/octet-stream")
    resp = client.post(
        attachment_upload_url(scenario["fleet"], scenario["draft_version"]), {"file": upload}
    )
    assert resp.status_code == 302
    assert not VersionAttachment.objects.filter(version=scenario["draft_version"]).exists()
    assert list(scenario["storage_dir"].iterdir()) == []


def test_upload_rejects_oversize_file(client, scenario, settings):
    settings.ATTACHMENT_MAX_BYTES = 10
    client.force_login(scenario["owner"])
    upload = SimpleUploadedFile(
        "codeplug.ctb", b"this is more than ten bytes", content_type="application/octet-stream"
    )
    resp = client.post(
        attachment_upload_url(scenario["fleet"], scenario["draft_version"]), {"file": upload}
    )
    assert resp.status_code == 302
    assert not VersionAttachment.objects.filter(version=scenario["draft_version"]).exists()
    assert list(scenario["storage_dir"].iterdir()) == []


def test_upload_cleans_up_file_when_db_create_fails(client, scenario, monkeypatch):
    client.force_login(scenario["owner"])

    def boom(**kwargs):
        raise RuntimeError("simulated database failure")

    monkeypatch.setattr(VersionAttachment.objects, "create", boom)
    upload = SimpleUploadedFile(
        "codeplug.ctb", b"some bytes", content_type="application/octet-stream"
    )

    with pytest.raises(RuntimeError):
        client.post(
            attachment_upload_url(scenario["fleet"], scenario["draft_version"]), {"file": upload}
        )

    assert not VersionAttachment.objects.filter(version=scenario["draft_version"]).exists()
    assert list(scenario["storage_dir"].iterdir()) == []


def test_viewer_can_download_but_not_upload(client, scenario):
    attachment = VersionAttachment.objects.create(
        fleet=scenario["fleet"],
        version=scenario["draft_version"],
        storage_key="deadbeef.ctb",
        original_filename="codeplug.ctb",
        byte_size=3,
        sha256="0" * 64,
        uploaded_by=scenario["owner"],
    )
    storage = get_attachment_storage()
    storage.save("deadbeef.ctb", SimpleUploadedFile("codeplug.ctb", b"abc"))

    client.force_login(scenario["viewer"])
    assert (
        client.get(
            attachment_download_url(scenario["fleet"], scenario["draft_version"], attachment)
        ).status_code
        == 200
    )

    upload = SimpleUploadedFile("codeplug2.ctb", b"xyz")
    resp = client.post(
        attachment_upload_url(scenario["fleet"], scenario["draft_version"]), {"file": upload}
    )
    assert resp.status_code == 403


def test_outsider_cannot_download_attachment(client, scenario):
    attachment = VersionAttachment.objects.create(
        fleet=scenario["fleet"],
        version=scenario["draft_version"],
        storage_key="deadbeef.ctb",
        original_filename="codeplug.ctb",
        byte_size=3,
        sha256="0" * 64,
        uploaded_by=scenario["owner"],
    )
    client.force_login(scenario["outsider"])
    resp = client.get(
        attachment_download_url(scenario["fleet"], scenario["draft_version"], attachment)
    )
    assert resp.status_code == 404


# --- Programming records ---


def test_only_published_versions_are_selectable_for_programming(client, scenario):
    client.force_login(scenario["owner"])
    resp = client.post(
        programming_create_url(scenario["fleet"], scenario["radio"]),
        {"version": scenario["draft_version"].pk, "programmed_at": "2026-09-20T10:00", "note": ""},
    )
    assert resp.status_code == 302  # redirects with an error, doesn't 500
    assert not scenario["radio"].programming_records.exists()


def test_editor_can_record_programming_of_published_version(client, scenario):
    client.force_login(scenario["editor"])
    resp = client.post(
        programming_create_url(scenario["fleet"], scenario["radio"]),
        {
            "version": scenario["published_version"].pk,
            "programmed_at": "2026-09-20T10:00",
            "note": "Race day flash",
        },
    )
    assert resp.status_code == 302
    record = scenario["radio"].programming_records.get()
    assert record.version == scenario["published_version"]
    assert record.note == "Race day flash"


def test_viewer_cannot_record_programming(client, scenario):
    client.force_login(scenario["viewer"])
    resp = client.post(
        programming_create_url(scenario["fleet"], scenario["radio"]),
        {"version": scenario["published_version"].pk, "programmed_at": "2026-09-20T10:00"},
    )
    assert resp.status_code == 403


def test_cannot_record_programming_with_a_cross_fleet_version(client, scenario):
    other_configuration = Configuration.objects.create(
        fleet=scenario["other_fleet"], name="Other Config", created_by=scenario["outsider"]
    )
    other_version = create_version(
        configuration=other_configuration, created_by=scenario["outsider"]
    )
    publish_version(other_version)

    client.force_login(scenario["owner"])
    resp = client.post(
        programming_create_url(scenario["fleet"], scenario["radio"]),
        {"version": other_version.pk, "programmed_at": "2026-09-20T10:00"},
    )
    assert resp.status_code == 302
    assert not scenario["radio"].programming_records.exists()


def test_outsider_cannot_record_programming(client, scenario):
    client.force_login(scenario["outsider"])
    resp = client.post(
        programming_create_url(scenario["fleet"], scenario["radio"]),
        {"version": scenario["published_version"].pk, "programmed_at": "2026-09-20T10:00"},
    )
    assert resp.status_code == 404


def test_latest_programming_record_is_shown_as_current(client, scenario):
    client.force_login(scenario["owner"])
    client.post(
        programming_create_url(scenario["fleet"], scenario["radio"]),
        {"version": scenario["published_version"].pk, "programmed_at": "2026-01-01T10:00"},
    )
    second_version = create_version(
        configuration=scenario["configuration"], created_by=scenario["owner"]
    )
    publish_version(second_version)
    client.post(
        programming_create_url(scenario["fleet"], scenario["radio"]),
        {"version": second_version.pk, "programmed_at": "2026-06-01T10:00"},
    )

    resp = client.get(
        reverse(
            "radios:detail",
            kwargs={
                "fleet_public_id": scenario["fleet"].public_id,
                "public_id": scenario["radio"].public_id,
            },
        )
    )
    assert resp.status_code == 200
    assert scenario["radio"].programming_records.count() == 2
    latest = scenario["radio"].programming_records.first()
    assert latest.version == second_version

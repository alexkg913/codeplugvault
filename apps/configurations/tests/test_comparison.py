import pytest
from django.contrib.auth import get_user_model

from apps.configurations.comparison import compare_versions
from apps.configurations.models import ChannelSnapshot, Configuration
from apps.configurations.services import create_version
from apps.fleets.services import create_personal_fleet

User = get_user_model()

pytestmark = pytest.mark.django_db


@pytest.fixture
def configuration():
    user = User.objects.create_user(username="owner", password="pw12345!")
    fleet = create_personal_fleet(user, "Fleet")
    return Configuration.objects.create(fleet=fleet, name="Race Weekend", created_by=user)


def make_channel(version, position, **kwargs):
    defaults = {"name": f"Ch {position}", "mode": "analog"}
    defaults.update(kwargs)
    return ChannelSnapshot.objects.create(
        fleet=version.fleet, version=version, position=position, **defaults
    )


def test_added_channel_detected(configuration):
    v1 = create_version(configuration=configuration, created_by=configuration.created_by)
    v2 = create_version(configuration=configuration, created_by=configuration.created_by)
    make_channel(v1, 1, name="Alpha")
    make_channel(v2, 1, name="Alpha")
    make_channel(v2, 2, name="Bravo")

    diff = compare_versions(v1, v2)
    assert [c.position for c in diff["added"]] == [2]
    assert diff["removed"] == []
    assert diff["changed"] == []
    assert diff["unchanged_count"] == 1


def test_removed_channel_detected(configuration):
    v1 = create_version(configuration=configuration, created_by=configuration.created_by)
    v2 = create_version(configuration=configuration, created_by=configuration.created_by)
    make_channel(v1, 1, name="Alpha")
    make_channel(v1, 2, name="Bravo")
    make_channel(v2, 1, name="Alpha")

    diff = compare_versions(v1, v2)
    assert [c.position for c in diff["removed"]] == [2]
    assert diff["added"] == []


def test_renamed_channel_detected_as_changed(configuration):
    v1 = create_version(configuration=configuration, created_by=configuration.created_by)
    v2 = create_version(configuration=configuration, created_by=configuration.created_by)
    make_channel(v1, 1, name="Alpha")
    make_channel(v2, 1, name="Alpha Prime")

    diff = compare_versions(v1, v2)
    assert len(diff["changed"]) == 1
    assert diff["changed"][0]["position"] == 1
    assert diff["changed"][0]["changed_fields"] == ["name"]


def test_frequency_change_detected(configuration):
    v1 = create_version(configuration=configuration, created_by=configuration.created_by)
    v2 = create_version(configuration=configuration, created_by=configuration.created_by)
    make_channel(v1, 1, rx_frequency="462.56250", tx_frequency="462.56250")
    make_channel(v2, 1, rx_frequency="462.60000", tx_frequency="462.56250")

    diff = compare_versions(v1, v2)
    assert diff["changed"][0]["changed_fields"] == ["rx_frequency"]


def test_identical_channel_is_unchanged(configuration):
    v1 = create_version(configuration=configuration, created_by=configuration.created_by)
    v2 = create_version(configuration=configuration, created_by=configuration.created_by)
    make_channel(v1, 1, name="Alpha", zone="Pit")
    make_channel(v2, 1, name="Alpha", zone="Pit")

    diff = compare_versions(v1, v2)
    assert diff["added"] == diff["removed"] == diff["changed"] == []
    assert diff["unchanged_count"] == 1


def test_swapping_which_channel_occupies_a_position_counts_as_a_change(configuration):
    """Position is the stable comparison key (it's the radio's memory slot),
    so moving what occupies a slot is real content, not cosmetic reordering.
    """
    v1 = create_version(configuration=configuration, created_by=configuration.created_by)
    v2 = create_version(configuration=configuration, created_by=configuration.created_by)
    make_channel(v1, 1, name="Alpha", zone="Pit")
    make_channel(v1, 2, name="Bravo", zone="Pit")
    # Same two channels, but swapped which position each occupies.
    make_channel(v2, 1, name="Bravo", zone="Pit")
    make_channel(v2, 2, name="Alpha", zone="Pit")

    diff = compare_versions(v1, v2)
    assert diff["added"] == []
    assert diff["removed"] == []
    changed_positions = {entry["position"] for entry in diff["changed"]}
    assert changed_positions == {1, 2}
    assert diff["unchanged_count"] == 0

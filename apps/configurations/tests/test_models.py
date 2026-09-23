import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from apps.configurations.models import ChannelSnapshot, Configuration, ConfigurationVersion
from apps.configurations.services import (
    VersionNotDraftError,
    create_version,
    publish_version,
)
from apps.fleets.services import create_personal_fleet

User = get_user_model()

pytestmark = pytest.mark.django_db


def make_fleet(name="Fleet"):
    user = User.objects.create_user(username=f"user-{name}", password="pw12345!")
    return create_personal_fleet(user, name)


def make_configuration(fleet, name="Race Weekend"):
    return Configuration.objects.create(fleet=fleet, name=name, created_by=fleet.created_by)


def test_duplicate_configuration_name_rejected_within_fleet():
    fleet = make_fleet("Fleet A")
    make_configuration(fleet, "Race Weekend")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            make_configuration(fleet, "Race Weekend")


def test_create_version_assigns_sequential_numbers():
    fleet = make_fleet("Fleet A")
    configuration = make_configuration(fleet)

    v1 = create_version(configuration=configuration, created_by=fleet.created_by)
    v2 = create_version(configuration=configuration, created_by=fleet.created_by)

    assert v1.version_number == 1
    assert v2.version_number == 2
    assert v1.state == ConfigurationVersion.State.DRAFT


def test_duplicate_version_number_rejected_at_db_level():
    fleet = make_fleet("Fleet A")
    configuration = make_configuration(fleet)
    ConfigurationVersion.objects.create(fleet=fleet, configuration=configuration, version_number=1)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ConfigurationVersion.objects.create(
                fleet=fleet, configuration=configuration, version_number=1
            )


def test_publish_version_freezes_state():
    fleet = make_fleet("Fleet A")
    configuration = make_configuration(fleet)
    version = create_version(configuration=configuration, created_by=fleet.created_by)

    publish_version(version)
    version.refresh_from_db()
    assert version.is_published
    assert version.published_at is not None


def test_publishing_twice_raises():
    fleet = make_fleet("Fleet A")
    configuration = make_configuration(fleet)
    version = create_version(configuration=configuration, created_by=fleet.created_by)
    publish_version(version)

    with pytest.raises(VersionNotDraftError):
        publish_version(version)


def test_duplicate_channel_position_rejected_at_db_level():
    fleet = make_fleet("Fleet A")
    configuration = make_configuration(fleet)
    version = create_version(configuration=configuration, created_by=fleet.created_by)
    ChannelSnapshot.objects.create(
        fleet=fleet, version=version, position=1, name="Ch 1", mode="analog"
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ChannelSnapshot.objects.create(
                fleet=fleet, version=version, position=1, name="Ch 1 dup", mode="analog"
            )

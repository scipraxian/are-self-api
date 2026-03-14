import os

import pytest

from identity.models import IdentityType, IdentityDisc
from identity.addons.addon_package import AddonPackage
from identity.addons import agile_addon as agile_module
from identity.addons.agile_addon import agile_addon
from prefrontal_cortex.models import PFCItemStatus, PFCEpic, PFCStory
from temporal_lobe.models import Shift


os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"


class _FakeDisc:
    def __init__(self, identity_type_id):
        self.identity_type_id = identity_type_id
        self.id = "fake-disc-id"
        self.identity_type = None


class _FakeDiscManager:
    def __init__(self, identity_type_id):
        self._disc = _FakeDisc(identity_type_id=identity_type_id)

    def select_related(self, *args, **kwargs):
        return self

    def get(self, id):
        return self._disc


class _EmptyQuerySet:
    def count(self):
        return 0

    def exists(self):
        return False

    def __iter__(self):
        return iter([])


class _EmptyManager:
    def filter(self, *args, **kwargs):
        return _EmptyQuerySet()


class _FakeStatus:
    def __init__(self, pk, name):
        self.pk = pk
        self.name = name


class _StatusManager:
    def all(self):
        return [
            _FakeStatus(pk=PFCItemStatus.BACKLOG, name="Backlog"),
        ]


def _make_package(
    iteration=1,
    identity="fake-identity-id",
    identity_disc="fake-disc-id",
    turn_number=1,
    reasoning_turn_id=1,
    environment_id="env-123",
    shift_id=None,
):
    return AddonPackage(
        iteration=iteration,
        identity=identity,
        identity_disc=identity_disc,
        turn_number=turn_number,
        reasoning_turn_id=reasoning_turn_id,
        environment_id=environment_id,
        shift_id=shift_id,
    )


def test_agile_addon_preview_mode_without_disc():
    """When no disc or reasoning turn is provided, addon stays in preview mode."""
    package = AddonPackage(
        iteration=None,
        identity=None,
        identity_disc=None,
        turn_number=1,
        reasoning_turn_id=None,
        environment_id=None,
        shift_id=None,
    )

    prompt = agile_addon(package)

    assert (
        prompt
        == "[AGILE BOARD CONTEXT: UI Preview Mode - No Active Disc Assigned]"
    )


def test_agile_addon_preview_mode_without_shift(monkeypatch):
    """With a disc but no shift_id, addon reports missing shift context."""
    # Avoid hitting the real DB for IdentityDisc
    monkeypatch.setattr(
        agile_module.IdentityDisc,
        "objects",
        _FakeDiscManager(identity_type_id=IdentityType.PM),
    )

    package = _make_package(shift_id=None)

    prompt = agile_addon(package)

    assert "No Active Shift or Disc Assigned" in prompt


def test_agile_addon_sifting_pm_context_for_pm(monkeypatch):
    """
    For a PM in the SIFTING shift, the addon should emit
    Agile board context with DoR guidance and environment info.
    """
    # Patch ORM access so we do not require a database
    monkeypatch.setattr(
        agile_module.IdentityDisc,
        "objects",
        _FakeDiscManager(identity_type_id=IdentityType.PM),
    )
    monkeypatch.setattr(
        agile_module.PFCEpic,
        "objects",
        _EmptyManager(),
    )
    monkeypatch.setattr(
        agile_module.PFCStory,
        "objects",
        _EmptyManager(),
    )
    monkeypatch.setattr(
        agile_module.PFCItemStatus,
        "objects",
        _StatusManager(),
    )

    package = _make_package(shift_id=Shift.SIFTING)

    prompt = agile_addon(package)

    # Header & environment
    assert "AGILE BOARD CONTEXT" in prompt
    assert "SHIFT:" in prompt
    assert "ENVIRONMENT: env-123" in prompt

    # Sifting PM guidance text
    assert "Definition of Ready (DoR)" in prompt
    assert "No stories or epics in need of refinement." in prompt

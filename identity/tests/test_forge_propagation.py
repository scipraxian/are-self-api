"""Forge propagation: avatar / selection_filter / category carry over."""

from common.tests.common_test_case import CommonTestCase
from hypothalamus.models import AIModelCategory, AIModelSelectionFilter
from identity.forge import forge_identity_disc
from identity.models import (
    Avatar,
    AvatarSelectedDisplayType,
    Identity,
)


class TestForgePropagatesBlueprintFields(CommonTestCase):
    """Assert forge_identity_disc carries avatar, selection_filter, category."""

    def setUp(self):
        super().setUp()
        self.avatar = Avatar.objects.create(
            name='Blueprint Avatar',
            display_id=AvatarSelectedDisplayType.EMOJI,
            emoji='🪪',
        )
        self.category = AIModelCategory.objects.create(
            name='Forge Test Category',
        )
        self.selection_filter = AIModelSelectionFilter.objects.create(
            name='Forge Test Filter',
        )
        self.base = Identity.objects.create(
            name='Forge Test Base',
            avatar=self.avatar,
            category=self.category,
            selection_filter=self.selection_filter,
            system_prompt_template='hello world',
        )

    def test_forge_propagates_three_fks(self):
        """Assert disc inherits avatar, category, and selection_filter."""
        disc = forge_identity_disc(self.base, custom_name='Forge Test Disc')
        assert disc.avatar_id == self.avatar.id
        assert disc.category_id == self.category.id
        assert disc.selection_filter_id == self.selection_filter.id
        assert disc.system_prompt_template == 'hello world'

    def test_forge_handles_none_blueprint_fields(self):
        """Assert forge does not break when base Identity has NULL FKs."""
        bare_base = Identity.objects.create(
            name='Bare Base',
            system_prompt_template='no extras',
        )
        disc = forge_identity_disc(bare_base, custom_name='Bare Disc')
        assert disc.avatar_id is None
        assert disc.category_id is None
        assert disc.selection_filter_id is None

"""AvatarNestingMixin: read-side nesting of full Avatar JSON.

The auto-generated DRF field for the ``avatar`` FK emits a UUID. The
mixin replaces that UUID with the full ``AvatarSerializer.data`` so the
UI never has to make a follow-up fetch per disc / identity. The write
contract is unchanged — PATCH still accepts a UUID for ``avatar``.
"""

from common.tests.common_test_case import CommonTestCase
from identity.avatars import AvatarNestingMixin
from identity.models import (
    Avatar,
    AvatarSelectedDisplayType,
    Identity,
    IdentityDisc,
)
from identity.serializers import IdentityDiscSerializer, IdentitySerializer
from temporal_lobe.serializers import IdentityDiscLightSerializer


class TestAvatarNestingOnIdentitySerializer(CommonTestCase):
    """Assert IdentitySerializer nests Avatar JSON on read."""

    def test_avatar_set_emits_nested_dict(self):
        """Assert the Identity serializer replaces avatar UUID with nested JSON."""
        avatar = Avatar.objects.create(
            name='Persona Face',
            display_id=AvatarSelectedDisplayType.EMOJI,
            emoji='🦊',
            tint_color='#ff8800',
        )
        identity = Identity.objects.create(
            name='Foxy Persona', avatar=avatar,
        )
        data = IdentitySerializer(identity).data
        assert isinstance(data['avatar'], dict), data['avatar']
        assert data['avatar']['id'] == str(avatar.id)
        assert data['avatar']['name'] == 'Persona Face'
        assert data['avatar']['emoji'] == '🦊'
        assert data['avatar']['tint_color'] == '#ff8800'
        assert (
            data['avatar']['display']['id']
            == AvatarSelectedDisplayType.EMOJI
        )

    def test_avatar_null_stays_null(self):
        """Assert no avatar means ``avatar`` stays None on the payload."""
        identity = Identity.objects.create(name='Plain Persona')
        data = IdentitySerializer(identity).data
        assert data['avatar'] is None


class TestAvatarNestingOnIdentityDiscSerializer(CommonTestCase):
    """Assert IdentityDiscSerializer nests Avatar JSON on read."""

    def test_avatar_set_emits_nested_dict(self):
        """Assert the disc serializer replaces avatar UUID with nested JSON."""
        avatar = Avatar.objects.create(
            name='Disc Face',
            display_id=AvatarSelectedDisplayType.URL,
            url='https://example.com/face.png',
        )
        disc = IdentityDisc.objects.create(name='Disc With Face', avatar=avatar)
        data = IdentityDiscSerializer(disc).data
        assert isinstance(data['avatar'], dict), data['avatar']
        assert data['avatar']['id'] == str(avatar.id)
        assert data['avatar']['url'] == 'https://example.com/face.png'
        assert (
            data['avatar']['display']['id'] == AvatarSelectedDisplayType.URL
        )

    def test_avatar_null_stays_null(self):
        """Assert disc with no avatar serializes ``avatar`` as None."""
        disc = IdentityDisc.objects.create(name='Disc No Face')
        data = IdentityDiscSerializer(disc).data
        assert data['avatar'] is None


class TestAvatarNestingOnIdentityDiscLightSerializer(CommonTestCase):
    """Assert the temporal_lobe Light serializer also nests Avatar JSON."""

    def test_avatar_set_emits_nested_dict(self):
        """Assert IdentityDiscLightSerializer nests Avatar payload too."""
        avatar = Avatar.objects.create(
            name='Light Face',
            display_id=AvatarSelectedDisplayType.EMOJI,
            emoji='🌟',
        )
        disc = IdentityDisc.objects.create(name='Light Disc', avatar=avatar)
        data = IdentityDiscLightSerializer(disc).data
        assert isinstance(data['avatar'], dict), data['avatar']
        assert data['avatar']['id'] == str(avatar.id)
        assert data['avatar']['emoji'] == '🌟'

    def test_avatar_null_stays_null(self):
        """Assert IdentityDiscLightSerializer leaves null avatar alone."""
        disc = IdentityDisc.objects.create(name='Light Disc Bare')
        data = IdentityDiscLightSerializer(disc).data
        assert data['avatar'] is None


class TestWriteContractStillAcceptsUUID(CommonTestCase):
    """Assert PATCH on the V2 endpoint still accepts a bare UUID for avatar.

    The mixin is read-only — the auto-generated ``PrimaryKeyRelatedField``
    must keep accepting a UUID on writes.
    """

    def test_patch_disc_avatar_with_uuid(self):
        """Assert PATCHing the IdentityDisc viewset with a UUID still binds."""
        avatar = Avatar.objects.create(
            name='Patchable Face',
            display_id=AvatarSelectedDisplayType.EMOJI,
            emoji='🐉',
        )
        disc = IdentityDisc.objects.create(name='Patchable Disc')
        url = f'/api/v2/identity-discs/{disc.pk}/'
        response = self.test_client.patch(
            url, {'avatar': str(avatar.id)}, format='json',
        )
        assert response.status_code == 200, response.data
        disc.refresh_from_db()
        assert disc.avatar_id == avatar.id

        # Read-side comes back nested.
        assert isinstance(response.data['avatar'], dict), response.data['avatar']
        assert response.data['avatar']['id'] == str(avatar.id)
        assert response.data['avatar']['emoji'] == '🐉'

    def test_patch_identity_avatar_with_uuid(self):
        """Assert PATCHing the Identity viewset with a UUID still binds."""
        avatar = Avatar.objects.create(
            name='Identity Face',
            display_id=AvatarSelectedDisplayType.EMOJI,
            emoji='🦄',
        )
        identity = Identity.objects.create(name='Identity Patchable')
        url = f'/api/v2/identities/{identity.pk}/'
        response = self.test_client.patch(
            url, {'avatar': str(avatar.id)}, format='json',
        )
        assert response.status_code == 200, response.data
        identity.refresh_from_db()
        assert identity.avatar_id == avatar.id

        assert isinstance(response.data['avatar'], dict), response.data['avatar']
        assert response.data['avatar']['id'] == str(avatar.id)


class TestMixinIsExportedFromAvatarsModule(CommonTestCase):
    """Assert AvatarNestingMixin is the documented surface."""

    def test_mixin_is_in_dunder_all(self):
        """Assert the mixin name is exported from identity.avatars."""
        from identity import avatars

        assert 'AvatarNestingMixin' in avatars.__all__
        assert avatars.AvatarNestingMixin is AvatarNestingMixin

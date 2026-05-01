"""Avatar viewset + media-write tests.

These tests redirect ``NEURAL_MODIFIER_GRAFTS_ROOT`` to a per-test tmp
directory so a stray ``display=FILE`` upload can never write into the
checked-out ``neuroplasticity/grafts/`` tree and can never be reached
by the loader-isolation guard's production-path check.
"""

import tempfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from common.tests.common_test_case import CommonTestCase
from identity.models import (
    Avatar,
    AvatarSelectedDisplayType,
    Identity,
)
from neuroplasticity.models import NeuralModifier, NeuralModifierStatus


class _AvatarTestBase(CommonTestCase):
    """Shared setup: tmp grafts root + a non-canonical INSTALLED bundle."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._tmp = tempfile.TemporaryDirectory()
        cls._grafts_root = Path(cls._tmp.name)
        cls._override = override_settings(
            NEURAL_MODIFIER_GRAFTS_ROOT=str(cls._grafts_root),
        )
        cls._override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._override.disable()
        cls._tmp.cleanup()
        super().tearDownClass()


class TestAvatarSelectedDisplayTypeFixture(_AvatarTestBase):
    """Assert the four display-type rows ship in genetic_immutables."""

    def test_four_display_types_present(self):
        names = set(
            AvatarSelectedDisplayType.objects.values_list('name', flat=True),
        )
        assert names == {'Generated', 'File', 'URL', 'Emoji'}

    def test_class_constants_resolve(self):
        """Assert PK constants on the class match fixture rows."""
        assert AvatarSelectedDisplayType.objects.get(
            pk=AvatarSelectedDisplayType.GENERATED,
        ).name == 'Generated'
        assert AvatarSelectedDisplayType.objects.get(
            pk=AvatarSelectedDisplayType.FILE,
        ).name == 'File'
        assert AvatarSelectedDisplayType.objects.get(
            pk=AvatarSelectedDisplayType.URL,
        ).name == 'URL'
        assert AvatarSelectedDisplayType.objects.get(
            pk=AvatarSelectedDisplayType.EMOJI,
        ).name == 'Emoji'


class TestAvatarViewSetCreate(_AvatarTestBase):
    """Assert AvatarViewSet.create handles all four display kinds."""

    def test_create_generated_default(self):
        """Assert a JSON POST with no display defaults to GENERATED."""
        response = self.test_client.post(
            '/api/v2/avatars/',
            {'name': 'Generated Default'},
            format='json',
        )
        assert response.status_code == 201, response.data
        row = Avatar.objects.get(pk=response.data['id'])
        assert row.display_id == AvatarSelectedDisplayType.GENERATED
        assert row.stored_filename is None
        assert row.original_filename is None
        # Default genome is INCUBATOR (the only selected_for_edit=True row
        # in genetic_immutables).
        assert row.genome_id == NeuralModifier.INCUBATOR

    def test_create_file_without_image(self):
        """Assert display=FILE without an image part creates a NULL-byte row."""
        response = self.test_client.post(
            '/api/v2/avatars/',
            {
                'name': 'File No Bytes',
                'display_id': AvatarSelectedDisplayType.FILE,
            },
            format='json',
        )
        assert response.status_code == 201, response.data
        row = Avatar.objects.get(pk=response.data['id'])
        assert row.display_id == AvatarSelectedDisplayType.FILE
        assert row.stored_filename is None
        assert row.original_filename is None

    def test_create_file_with_image_writes_bytes(self):
        """Assert display=FILE + image part writes <uuid>.<ext> under grafts."""
        upload = SimpleUploadedFile(
            'portrait.PNG',
            b'\x89PNG\r\n\x1a\nFAKEBYTES',
            content_type='image/png',
        )
        response = self.test_client.post(
            '/api/v2/avatars/',
            {
                'name': 'File With Bytes',
                'display_id': AvatarSelectedDisplayType.FILE,
                'image': upload,
            },
            format='multipart',
        )
        assert response.status_code == 201, response.data
        row = Avatar.objects.get(pk=response.data['id'])
        assert row.display_id == AvatarSelectedDisplayType.FILE
        assert row.original_filename == 'portrait.PNG'
        assert row.stored_filename == f'{row.id}.png'

        incubator_slug = NeuralModifier.objects.get(
            pk=NeuralModifier.INCUBATOR,
        ).slug
        target = (
            self._grafts_root / incubator_slug / 'media' / row.stored_filename
        )
        assert target.exists()
        assert target.read_bytes() == b'\x89PNG\r\n\x1a\nFAKEBYTES'
        # Also assert the bytes did NOT land under the production grafts
        # directory inside the repo.
        repo_grafts = (
            Path(__file__).resolve().parents[2]
            / 'neuroplasticity'
            / 'grafts'
        )
        assert not (
            repo_grafts / incubator_slug / 'media' / row.stored_filename
        ).exists()

    def test_create_image_silently_ignored_for_non_file_display(self):
        """Assert an image part is dropped on a GENERATED-display row."""
        upload = SimpleUploadedFile(
            'noise.png', b'IGNORED', content_type='image/png',
        )
        response = self.test_client.post(
            '/api/v2/avatars/',
            {
                'name': 'Generated Plus File Part',
                'display_id': AvatarSelectedDisplayType.GENERATED,
                'image': upload,
            },
            format='multipart',
        )
        assert response.status_code == 201, response.data
        row = Avatar.objects.get(pk=response.data['id'])
        assert row.display_id == AvatarSelectedDisplayType.GENERATED
        assert row.stored_filename is None
        assert row.original_filename is None
        # No file matching THIS row's id was written. Earlier tests in the
        # same class may have populated the shared media dir; the
        # filesystem doesn't roll back with the DB transaction, so we
        # assert per-row instead of "media dir is empty."
        incubator_slug = NeuralModifier.objects.get(
            pk=NeuralModifier.INCUBATOR,
        ).slug
        media_dir = self._grafts_root / incubator_slug / 'media'
        if media_dir.exists():
            for entry in media_dir.iterdir():
                assert not entry.name.startswith(str(row.id))

    def test_create_url_kind(self):
        """Assert display=URL stores the url and leaves filename fields NULL."""
        response = self.test_client.post(
            '/api/v2/avatars/',
            {
                'name': 'External Image',
                'display_id': AvatarSelectedDisplayType.URL,
                'url': 'https://example.com/portrait.png',
            },
            format='json',
        )
        assert response.status_code == 201, response.data
        row = Avatar.objects.get(pk=response.data['id'])
        assert row.display_id == AvatarSelectedDisplayType.URL
        assert row.url == 'https://example.com/portrait.png'
        assert row.stored_filename is None

    def test_create_emoji_kind(self):
        """Assert display=EMOJI stores the glyph + tint."""
        response = self.test_client.post(
            '/api/v2/avatars/',
            {
                'name': 'Emoji Avatar',
                'display_id': AvatarSelectedDisplayType.EMOJI,
                'emoji': '🦊',
                'tint_color': '#ff8800',
            },
            format='json',
        )
        assert response.status_code == 201, response.data
        row = Avatar.objects.get(pk=response.data['id'])
        assert row.display_id == AvatarSelectedDisplayType.EMOJI
        assert row.emoji == '🦊'
        assert row.tint_color == '#ff8800'


class TestAvatarViewSetPatch(_AvatarTestBase):
    """Assert PATCH paths on AvatarViewSet."""

    def setUp(self):
        super().setUp()
        self.row = Avatar.objects.create(
            name='Patch Target',
            display_id=AvatarSelectedDisplayType.FILE,
        )

    def test_patch_adds_image_to_existing_file_row(self):
        """Assert PATCH with image fills stored_filename + writes bytes."""
        upload = SimpleUploadedFile(
            'avatar.jpg', b'JPEGBYTES', content_type='image/jpeg',
        )
        url = f'/api/v2/avatars/{self.row.pk}/'
        response = self.test_client.patch(
            url, {'image': upload}, format='multipart',
        )
        assert response.status_code == 200, response.data
        self.row.refresh_from_db()
        assert self.row.original_filename == 'avatar.jpg'
        assert self.row.stored_filename == f'{self.row.id}.jpg'

        incubator_slug = NeuralModifier.objects.get(
            pk=NeuralModifier.INCUBATOR,
        ).slug
        target = (
            self._grafts_root
            / incubator_slug
            / 'media'
            / self.row.stored_filename
        )
        assert target.exists()
        assert target.read_bytes() == b'JPEGBYTES'

    def test_patch_no_image_part_leaves_filename_fields(self):
        """Assert a JSON-only PATCH does not clobber filename fields."""
        # Pre-populate as if a previous upload happened.
        Avatar.objects.filter(pk=self.row.pk).update(
            original_filename='old.png',
            stored_filename=f'{self.row.id}.png',
        )
        url = f'/api/v2/avatars/{self.row.pk}/'
        response = self.test_client.patch(
            url, {'description': 'now with notes'}, format='json',
        )
        assert response.status_code == 200, response.data
        self.row.refresh_from_db()
        assert self.row.original_filename == 'old.png'
        assert self.row.stored_filename == f'{self.row.id}.png'
        assert self.row.description == 'now with notes'

    def test_patch_into_canonical_refused(self):
        """Assert PATCHing genome=canonical is refused with a 400."""
        url = f'/api/v2/avatars/{self.row.pk}/'
        response = self.test_client.patch(
            url, {'genome': str(NeuralModifier.CANONICAL)}, format='json',
        )
        assert response.status_code == 400, response.data
        # No restart fired (canonical refusal short-circuits before save).
        self.row.refresh_from_db()
        assert self.row.genome_id == NeuralModifier.INCUBATOR


class TestAvatarFKOnIdentity(_AvatarTestBase):
    """Assert the new ``avatar`` FK is wired into Identity / IdentityDisc."""

    def test_identity_can_point_at_avatar(self):
        """Assert assigning an avatar to an Identity persists."""
        avatar = Avatar.objects.create(
            name='Thalamus Face',
            display_id=AvatarSelectedDisplayType.EMOJI,
            emoji='🧠',
        )
        identity = Identity.objects.create(name='Test Persona')
        identity.avatar = avatar
        identity.save()
        identity.refresh_from_db()
        assert identity.avatar_id == avatar.id

    def test_avatar_delete_sets_identity_avatar_null(self):
        """Assert SET_NULL on the FK survives Avatar deletion."""
        avatar = Avatar.objects.create(
            name='Disposable Face',
            display_id=AvatarSelectedDisplayType.EMOJI,
            emoji='👻',
        )
        identity = Identity.objects.create(
            name='Persona With Disposable Face', avatar=avatar,
        )
        avatar.delete()
        identity.refresh_from_db()
        assert identity.avatar_id is None


class TestAvatarMediaDirHelper(_AvatarTestBase):
    """Assert the avatar_media_dir helper resolves under the active grafts root."""

    def test_avatar_media_dir_under_grafts_root(self):
        from identity.avatars import avatar_media_dir

        incubator = NeuralModifier.objects.get(pk=NeuralModifier.INCUBATOR)
        path = avatar_media_dir(incubator)
        assert path == self._grafts_root / incubator.slug / 'media'

    def test_avatar_storage_module_is_canonical_helper(self):
        """Assert avatars.py re-exports the helper from avatar_storage."""
        from identity import avatar_storage, avatars

        assert avatars.avatar_media_dir is avatar_storage.avatar_media_dir


class TestAvatarSaveMovesBytes(_AvatarTestBase):
    """Assert Avatar.save() moves the on-disk bytes when genome changes."""

    def setUp(self):
        super().setUp()
        # A second INSTALLED bundle the row can be promoted into.
        self.target_genome = NeuralModifier.objects.create(
            slug='test-target-bundle',
            name='Test Target',
            version='0.0.1',
            author='tests',
            license='MIT',
            manifest_hash='',
            manifest_json={},
            status_id=NeuralModifierStatus.INSTALLED,
        )

    def _seed_file_row(self, payload: bytes = b'BYTES') -> Avatar:
        row = Avatar.objects.create(
            name='Movable Avatar',
            display_id=AvatarSelectedDisplayType.FILE,
        )
        Avatar.objects.filter(pk=row.pk).update(
            original_filename='portrait.png',
            stored_filename=f'{row.id}.png',
        )
        row.refresh_from_db()
        incubator_slug = NeuralModifier.objects.get(
            pk=NeuralModifier.INCUBATOR,
        ).slug
        media_dir = self._grafts_root / incubator_slug / 'media'
        media_dir.mkdir(parents=True, exist_ok=True)
        (media_dir / row.stored_filename).write_bytes(payload)
        return row

    def test_genome_change_moves_file(self):
        """Assert promoting a FILE row carries its bytes to the new graft dir."""
        row = self._seed_file_row(b'PIXELS')
        incubator_slug = NeuralModifier.objects.get(
            pk=NeuralModifier.INCUBATOR,
        ).slug
        old_path = (
            self._grafts_root / incubator_slug / 'media' / row.stored_filename
        )
        new_path = (
            self._grafts_root
            / self.target_genome.slug
            / 'media'
            / row.stored_filename
        )

        row.genome = self.target_genome
        row.save()

        assert not old_path.exists()
        assert new_path.exists()
        assert new_path.read_bytes() == b'PIXELS'

    def test_genome_unchanged_no_move(self):
        """Assert saving a FILE row without changing genome leaves bytes put."""
        row = self._seed_file_row(b'STILL HERE')
        incubator_slug = NeuralModifier.objects.get(
            pk=NeuralModifier.INCUBATOR,
        ).slug
        old_path = (
            self._grafts_root / incubator_slug / 'media' / row.stored_filename
        )

        row.description = 'just a label change'
        row.save()

        assert old_path.exists()
        assert old_path.read_bytes() == b'STILL HERE'

    def test_non_file_display_no_move(self):
        """Assert genome change on a GENERATED row does not touch disk."""
        row = Avatar.objects.create(
            name='Generated Mover',
            display_id=AvatarSelectedDisplayType.GENERATED,
        )
        # Stash a stray file at the FILE-row path to prove the save() did
        # not naively move based on stored_filename alone.
        incubator_slug = NeuralModifier.objects.get(
            pk=NeuralModifier.INCUBATOR,
        ).slug
        media_dir = self._grafts_root / incubator_slug / 'media'
        media_dir.mkdir(parents=True, exist_ok=True)
        bait = media_dir / f'{row.id}.png'
        bait.write_bytes(b'DO NOT MOVE')

        row.genome = self.target_genome
        row.save()

        # Bait remains. Nothing landed under the target's media dir for
        # this row's id.
        assert bait.exists()
        assert bait.read_bytes() == b'DO NOT MOVE'
        target_dir = (
            self._grafts_root / self.target_genome.slug / 'media'
        )
        if target_dir.exists():
            for entry in target_dir.iterdir():
                assert not entry.name.startswith(str(row.id))

    def test_genome_change_with_no_stored_bytes_no_op(self):
        """Assert a FILE row created without bytes survives a genome move."""
        row = Avatar.objects.create(
            name='Empty File Row',
            display_id=AvatarSelectedDisplayType.FILE,
        )
        # No stored_filename, no bytes anywhere.
        row.genome = self.target_genome
        row.save()
        # No exception, no file was written for THIS row's id (other
        # sibling tests in the class share the same on-disk media dir;
        # filesystem doesn't roll back with the DB transaction).
        target_dir = (
            self._grafts_root / self.target_genome.slug / 'media'
        )
        if target_dir.exists():
            for entry in target_dir.iterdir():
                assert not entry.name.startswith(str(row.id))

    def test_genome_change_via_patch_endpoint_moves_file(self):
        """Assert the V2 PATCH path moves bytes the same as direct save()."""
        row = self._seed_file_row(b'API PIXELS')
        incubator_slug = NeuralModifier.objects.get(
            pk=NeuralModifier.INCUBATOR,
        ).slug
        old_path = (
            self._grafts_root / incubator_slug / 'media' / row.stored_filename
        )

        url = f'/api/v2/avatars/{row.pk}/'
        response = self.test_client.patch(
            url, {'genome': str(self.target_genome.pk)}, format='json',
        )
        assert response.status_code == 200, response.data
        assert response.data.get('restart_imminent') is True

        row.refresh_from_db()
        assert row.genome_id == self.target_genome.pk
        new_path = (
            self._grafts_root
            / self.target_genome.slug
            / 'media'
            / row.stored_filename
        )
        assert not old_path.exists()
        assert new_path.exists()
        assert new_path.read_bytes() == b'API PIXELS'

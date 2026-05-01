"""Tests for /api/v2/genomes/<slug>/media/<filename>.

The resolver is the single core route bundles share — every Avatar
``display=FILE`` row resolves through here. These tests redirect the
grafts root to a tmp directory so no production graft is ever read.
"""

import tempfile
from pathlib import Path

from django.test import override_settings

from common.tests.common_test_case import CommonTestCase
from neuroplasticity.models import NeuralModifier, NeuralModifierStatus


class _MediaResolverBase(CommonTestCase):
    """Shared setup: tmp grafts root + an INSTALLED non-canonical bundle."""

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

    def setUp(self):
        super().setUp()
        self.bundle = NeuralModifier.objects.create(
            slug='media-resolver-target',
            name='Media Resolver Target',
            version='0.0.1',
            author='tests',
            license='MIT',
            manifest_hash='',
            manifest_json={},
            status_id=NeuralModifierStatus.INSTALLED,
        )
        self.media_dir = self._grafts_root / self.bundle.slug / 'media'
        self.media_dir.mkdir(parents=True, exist_ok=True)


class TestGenomeMediaResolverHappyPath(_MediaResolverBase):
    def test_serves_existing_file_bytes(self):
        """Assert a hit returns the raw bytes."""
        payload = b'\x89PNG\r\n\x1a\nHELLO'
        (self.media_dir / 'face.png').write_bytes(payload)
        response = self.test_client.get(
            f'/api/v2/genomes/{self.bundle.slug}/media/face.png',
        )
        assert response.status_code == 200, response
        # FileResponse streams; collect chunks before comparing.
        body = b''.join(response.streaming_content)
        assert body == payload


class TestGenomeMediaResolverRefusals(_MediaResolverBase):
    def test_unknown_slug_404(self):
        """Assert a slug with no installed bundle gets 404."""
        response = self.test_client.get(
            '/api/v2/genomes/no-such-bundle/media/whatever.png',
        )
        assert response.status_code == 404

    def test_canonical_slug_404(self):
        """Assert canonical slug is refused even when filesystem has it."""
        # Place a file under the canonical media dir to prove the refusal
        # is by-policy, not by-absence.
        canonical_dir = self._grafts_root / 'canonical' / 'media'
        canonical_dir.mkdir(parents=True, exist_ok=True)
        (canonical_dir / 'forbidden.png').write_bytes(b'NOPE')
        response = self.test_client.get(
            '/api/v2/genomes/canonical/media/forbidden.png',
        )
        assert response.status_code == 404

    def test_non_installed_bundle_404(self):
        """Assert a BROKEN-status bundle does not resolve."""
        self.bundle.status_id = NeuralModifierStatus.BROKEN
        self.bundle.save(update_fields=['status'])
        (self.media_dir / 'face.png').write_bytes(b'BYTES')
        response = self.test_client.get(
            f'/api/v2/genomes/{self.bundle.slug}/media/face.png',
        )
        assert response.status_code == 404

    def test_missing_file_404(self):
        """Assert a hit for a non-existent file returns 404."""
        response = self.test_client.get(
            f'/api/v2/genomes/{self.bundle.slug}/media/missing.png',
        )
        assert response.status_code == 404

    def test_dot_dot_filename_400(self):
        """Assert a literal `..` filename is rejected as 400."""
        response = self.test_client.get(
            f'/api/v2/genomes/{self.bundle.slug}/media/..',
        )
        assert response.status_code == 400

    def test_dotfile_400(self):
        """Assert a leading dot in the filename is rejected as 400."""
        (self.media_dir / '.hidden').write_bytes(b'SECRET')
        response = self.test_client.get(
            f'/api/v2/genomes/{self.bundle.slug}/media/.hidden',
        )
        assert response.status_code == 400

    def test_slash_in_filename_404(self):
        """Assert a slash in the filename never reaches the view (router rejects)."""
        # The <str:filename> URL converter matches [^/]+, so a slash in
        # the path produces a router-level 404 before the view runs.
        response = self.test_client.get(
            f'/api/v2/genomes/{self.bundle.slug}/media/sub/file.png',
        )
        assert response.status_code == 404

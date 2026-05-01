"""composite_vector on IdentityDiscSerializer.

Centroid of identity vector + every attached engram vector,
unit-normalized. None when there's nothing to embed or the sum is zero.
"""

import numpy as np

from common.tests.common_test_case import CommonTestCase
from hippocampus.models import Engram
from identity.models import IdentityDisc
from identity.serializers import IdentityDiscSerializer


def _vec(value: float) -> list:
    """Build a 768-d vector filled with ``value``."""
    return [value] * 768


def _alternating(value: float) -> list:
    """Build a 768-d vector that alternates ±value (zero-sum-friendly)."""
    return [value if i % 2 == 0 else -value for i in range(768)]


class TestCompositeVectorNullCases(CommonTestCase):
    """Assert composite_vector returns None when there's nothing to embed."""

    def test_no_vector_no_memories_returns_none(self):
        """Assert disc with no identity vector + no engrams → None."""
        disc = IdentityDisc.objects.create(name='Empty Disc')
        # Disc has no vector_node, no engrams attached.
        assert disc.vector is None
        assert disc.engrams.count() == 0

        data = IdentityDiscSerializer(disc).data
        assert data['composite_vector'] is None

    def test_engrams_with_null_vectors_skipped(self):
        """Assert engrams missing a vector don't crash and don't contribute."""
        disc = IdentityDisc.objects.create(name='Disc With Vectorless Engrams')
        # Engrams without vectors. Engram.save() in this codebase only
        # auto-vectorizes on description change of an existing row, so
        # creating with vector=None lands a row whose vector stays NULL.
        for i in range(3):
            engram = Engram.objects.create(
                name=f'Vectorless Engram {i}',
                description=f'no vector {i}',
                vector=None,
            )
            disc.engrams.add(engram)
        assert disc.vector is None

        data = IdentityDiscSerializer(disc).data
        # Only vectorless engrams + no identity vector → no components.
        assert data['composite_vector'] is None

    def test_zero_sum_vectors_returns_none(self):
        """Assert opposing vectors that sum to zero collapse to None."""
        disc = IdentityDisc.objects.create(name='Zero Sum Disc')
        # Two engrams whose vectors are exact negatives → element-wise
        # sum is the zero vector → norm is 0 → composite is None.
        e_pos = Engram.objects.create(
            name='Pos', description='positive', vector=_alternating(0.5),
        )
        e_neg = Engram.objects.create(
            name='Neg',
            description='negative',
            vector=[-x for x in _alternating(0.5)],
        )
        disc.engrams.add(e_pos)
        disc.engrams.add(e_neg)
        assert disc.vector is None

        data = IdentityDiscSerializer(disc).data
        assert data['composite_vector'] is None


class TestCompositeVectorHappyPath(CommonTestCase):
    """Assert composite_vector returns a unit-normalized 768-d vector."""

    def test_identity_vector_only(self):
        """Assert with no engrams, the field returns the unit-normalized identity vector."""
        disc = IdentityDisc.objects.create(name='Solo Disc')
        disc.vector = np.asarray(_vec(0.25), dtype=float)
        # IdentityDisc.vector setter writes through a 1:1 vector_node.

        data = IdentityDiscSerializer(disc).data
        composite = data['composite_vector']
        assert composite is not None
        assert len(composite) == 768

        # Each component of [0.25] * 768, normalized, equals 1/sqrt(768).
        expected = 1.0 / (768 ** 0.5)
        for value in composite:
            assert abs(value - expected) < 1e-9

        # Unit length.
        norm = sum(v * v for v in composite) ** 0.5
        assert abs(norm - 1.0) < 1e-9

    def test_only_engrams_no_identity_vector(self):
        """Assert with no identity vector, engrams alone drive the centroid."""
        disc = IdentityDisc.objects.create(name='Memory-Only Disc')
        assert disc.vector is None
        for i in range(2):
            engram = Engram.objects.create(
                name=f'Mem {i}',
                description=f'memory {i}',
                vector=_vec(0.5),
            )
            disc.engrams.add(engram)

        data = IdentityDiscSerializer(disc).data
        composite = data['composite_vector']
        assert composite is not None
        assert len(composite) == 768

        # Sum of two [0.5]*768 → [1.0]*768 → unit-normalized = 1/sqrt(768).
        expected = 1.0 / (768 ** 0.5)
        for value in composite:
            assert abs(value - expected) < 1e-9

    def test_identity_plus_engrams_centroid(self):
        """Assert identity + engram vectors sum element-wise then normalize."""
        disc = IdentityDisc.objects.create(name='Combined Disc')
        disc.vector = np.asarray(_vec(0.3), dtype=float)
        e1 = Engram.objects.create(
            name='Mem A', description='aaa', vector=_vec(0.2),
        )
        e2 = Engram.objects.create(
            name='Mem B', description='bbb', vector=_vec(0.5),
        )
        disc.engrams.add(e1, e2)

        data = IdentityDiscSerializer(disc).data
        composite = data['composite_vector']
        assert composite is not None
        assert len(composite) == 768

        # Sum: 0.3 + 0.2 + 0.5 = 1.0 per element. Norm: sqrt(768).
        # Each element: 1.0 / sqrt(768).
        expected = 1.0 / (768 ** 0.5)
        for value in composite:
            assert abs(value - expected) < 1e-9

    def test_vectorless_engram_does_not_corrupt_centroid(self):
        """Assert a NULL-vector engram is skipped without affecting the result."""
        disc = IdentityDisc.objects.create(name='Mixed Engrams Disc')
        disc.vector = np.asarray(_vec(0.5), dtype=float)
        with_vector = Engram.objects.create(
            name='Has Vec', description='has', vector=_vec(0.5),
        )
        no_vector = Engram.objects.create(
            name='No Vec', description='none', vector=None,
        )
        disc.engrams.add(with_vector, no_vector)

        data = IdentityDiscSerializer(disc).data
        composite = data['composite_vector']
        assert composite is not None
        # Identity (0.5) + with_vector (0.5) per element = 1.0; no_vector
        # is skipped. Normalized: 1/sqrt(768).
        expected = 1.0 / (768 ** 0.5)
        for value in composite:
            assert abs(value - expected) < 1e-9

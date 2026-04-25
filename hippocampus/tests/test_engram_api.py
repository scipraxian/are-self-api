import pytest
from django.test import TestCase
from rest_framework.test import APIClient

from common.tests.common_test_case import CommonFixturesAPITestCase
from frontal_lobe.models import ReasoningSession, ReasoningStatusID
from hippocampus.models import Engram
from identity.models import IdentityDisc


class TestEngramFilterBySession(CommonFixturesAPITestCase):
    """Assert EngramViewSet filters by sessions query param."""

    def setUp(self):
        super().setUp()
        self.session_linked = ReasoningSession.objects.create(
            status_id=ReasoningStatusID.ACTIVE
        )
        self.session_other = ReasoningSession.objects.create(
            status_id=ReasoningStatusID.ACTIVE
        )

        self.engram_linked = Engram.objects.create(
            name='Memory linked',
            description='Linked to session_linked',
        )
        self.engram_linked.sessions.add(self.session_linked)

        self.engram_unlinked = Engram.objects.create(
            name='Memory unlinked',
            description='Not linked to session_linked',
        )

    def test_filter_engrams_by_session(self):
        """Assert filtering by sessions returns only linked engrams."""
        response = self.test_client.get(
            '/api/v2/engrams/',
            {'sessions': str(self.session_linked.pk)},
        )
        assert response.status_code == 200
        returned_ids = {item['id'] for item in response.data}
        assert str(self.engram_linked.pk) in returned_ids
        assert str(self.engram_unlinked.pk) not in returned_ids


class TestEngramFilterByIdentityDisc(CommonFixturesAPITestCase):
    """Assert EngramViewSet filters by identity_discs query param."""

    def setUp(self):
        super().setUp()
        self.disc_a = IdentityDisc.objects.first()
        self.disc_b = IdentityDisc.objects.exclude(
            pk=self.disc_a.pk
        ).first()

        self.engram_a = Engram.objects.create(
            name='Memory A',
            description='Belongs to disc A',
        )
        self.engram_a.identity_discs.add(self.disc_a)

        self.engram_b = Engram.objects.create(
            name='Memory B',
            description='Belongs to disc B',
        )
        self.engram_b.identity_discs.add(self.disc_b)

        self.engram_both = Engram.objects.create(
            name='Memory Both',
            description='Belongs to both discs',
        )
        self.engram_both.identity_discs.add(self.disc_a, self.disc_b)

    def test_filter_engrams_by_identity_disc(self):
        """Assert filtering by identity_discs returns only matching engrams."""
        response = self.test_client.get(
            '/api/v2/engrams/',
            {'identity_discs': str(self.disc_a.pk)},
        )
        assert response.status_code == 200
        returned_ids = {item['id'] for item in response.data}
        assert str(self.engram_a.pk) in returned_ids
        assert str(self.engram_both.pk) in returned_ids
        assert str(self.engram_b.pk) not in returned_ids

    def test_no_filter_returns_all(self):
        """Assert omitting identity_discs returns all engrams."""
        response = self.test_client.get('/api/v2/engrams/')
        assert response.status_code == 200
        returned_ids = {item['id'] for item in response.data}
        assert str(self.engram_a.pk) in returned_ids
        assert str(self.engram_b.pk) in returned_ids
        assert str(self.engram_both.pk) in returned_ids

    def test_filter_returns_no_duplicates(self):
        """Assert filtering with M2M join does not duplicate rows."""
        self.engram_a.identity_discs.add(self.disc_b)
        response = self.test_client.get(
            '/api/v2/engrams/',
            {'identity_discs': str(self.disc_a.pk)},
        )
        ids = [item['id'] for item in response.data]
        assert len(ids) == len(set(ids))

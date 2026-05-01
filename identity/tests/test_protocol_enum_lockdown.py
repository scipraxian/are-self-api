"""Protocol-enum viewsets are read-only.

IdentityType, BudgetPeriod, IdentityAddonPhase, AvatarSelectedDisplayType:
class-constant rows owned by code, fixture-shipped, never mutated at
runtime. This test pins that contract — POST/PATCH/DELETE return 405.
"""

from common.tests.common_test_case import CommonTestCase
from identity.models import (
    AvatarSelectedDisplayType,
    BudgetPeriod,
    IdentityAddonPhase,
    IdentityType,
)


class TestProtocolEnumViewsetsAreReadOnly(CommonTestCase):
    """Assert the four protocol-enum viewsets refuse writes."""

    BASES = (
        ('/api/v2/identity_types/', IdentityType),
        ('/api/v2/budget-periods/', BudgetPeriod),
        ('/api/v2/identity-addon-phases/', IdentityAddonPhase),
        ('/api/v2/avatar-display-types/', AvatarSelectedDisplayType),
    )

    def test_get_list_works(self):
        """Assert GET on each protocol-enum surface returns 200."""
        for url, _ in self.BASES:
            response = self.test_client.get(url)
            assert response.status_code == 200, (url, response.status_code)

    def test_post_refused(self):
        """Assert POST is 405 on each protocol-enum surface."""
        for url, _ in self.BASES:
            response = self.test_client.post(
                url, {'name': 'Should Not Land'}, format='json',
            )
            assert response.status_code == 405, (url, response.status_code)

    def test_patch_refused(self):
        """Assert PATCH on a detail row is 405."""
        for url, model in self.BASES:
            row = model.objects.first()
            assert row is not None, f'No fixture row for {model}'
            response = self.test_client.patch(
                f'{url}{row.pk}/',
                {'name': 'Should Not Mutate'},
                format='json',
            )
            assert response.status_code == 405, (url, response.status_code)

    def test_delete_refused(self):
        """Assert DELETE on a detail row is 405."""
        for url, model in self.BASES:
            row = model.objects.first()
            assert row is not None, f'No fixture row for {model}'
            response = self.test_client.delete(f'{url}{row.pk}/')
            assert response.status_code == 405, (url, response.status_code)

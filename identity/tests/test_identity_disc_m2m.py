from common.tests.common_test_case import CommonFixturesAPITestCase
from identity.models import IdentityAddon, IdentityDisc, IdentityTag
from parietal_lobe.models import ToolDefinition


class TestIdentityDiscM2MWrite(CommonFixturesAPITestCase):
    """Assert PATCHing M2M fields on IdentityDisc persists relationships."""

    def setUp(self):
        super().setUp()
        self.disc = IdentityDisc.objects.first()
        self.tool = ToolDefinition.objects.first()
        self.addon = IdentityAddon.objects.first()
        self.tag = IdentityTag.objects.first()

    def test_patch_m2m_fields_persists(self):
        """Assert PATCHing enabled_tool_ids, addon_ids, tag_ids sets M2M relations."""
        url = f'/api/v2/identity-discs/{self.disc.pk}/'
        response = self.test_client.patch(
            url,
            {
                'enabled_tool_ids': [self.tool.pk],
                'addon_ids': [self.addon.pk],
                'tag_ids': [self.tag.pk],
            },
            format='json',
        )
        assert response.status_code == 200, response.data

        self.disc.refresh_from_db()
        assert self.tool in self.disc.enabled_tools.all()
        assert self.addon in self.disc.addons.all()
        assert self.tag in self.disc.tags.all()

    def test_patch_m2m_clear(self):
        """Assert PATCHing with empty lists clears M2M relations."""
        self.disc.enabled_tools.add(self.tool)
        self.disc.addons.add(self.addon)
        self.disc.tags.add(self.tag)

        url = f'/api/v2/identity-discs/{self.disc.pk}/'
        response = self.test_client.patch(
            url,
            {
                'enabled_tool_ids': [],
                'addon_ids': [],
                'tag_ids': [],
            },
            format='json',
        )
        assert response.status_code == 200, response.data

        self.disc.refresh_from_db()
        assert self.disc.enabled_tools.count() == 0
        assert self.disc.addons.count() == 0
        assert self.disc.tags.count() == 0

    def test_read_returns_nested_objects(self):
        """Assert GET returns nested serialized objects, not bare IDs."""
        self.disc.enabled_tools.set([self.tool])
        url = f'/api/v2/identity-discs/{self.disc.pk}/'
        response = self.test_client.get(url)
        assert response.status_code == 200
        tools = response.data['enabled_tools']
        assert len(tools) == 1
        assert isinstance(tools[0], dict)
        assert tools[0]['id'] == str(self.tool.pk)

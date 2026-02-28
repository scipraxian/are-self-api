from django.test import Client, TestCase
from django.urls import reverse


class FrontendMigrationTests(TestCase):
    """
    Verifies that the frontend migration to the API-driven architecture
    has been successfully applied to the dashboard.
    """

    def setUp(self):
        self.client = Client()

    def test_new_architecture_present(self):
        """
        Ensures the new container, scripts, and templates are present.
        """
        response = self.client.get(reverse('dashboard:home'))
        self.assertEqual(response.status_code, 200)

        # 1. Check for the new DOM target
        self.assertContains(response,
                            'id="spawns-dispatcher-root"',
                            msg_prefix="Missing new DOM target for spawns")
        self.assertNotContains(
            response,
            'id="mission-monitor"',
            msg_prefix="Old mission-monitor div should be removed")

        # 2. Check for new JS assets
        self.assertContains(response,
                            '/central_nervous_system/js/cns_head.js',
                            msg_prefix="Missing cns_head.js")
        self.assertContains(response,
                            '/central_nervous_system/js/cns_spawns.js',
                            msg_prefix="Missing cns_spawns.js")
        self.assertContains(response,
                            '/central_nervous_system/js/cns_spawn.js',
                            msg_prefix="Missing cns_spawn.js")
        self.assertContains(response,
                            '/central_nervous_system/js/cns_spawn_control_card.js',
                            msg_prefix="Missing cns_spawn_control_card.js")

        # 3. Check for new CSS assets
        self.assertContains(response,
                            '/central_nervous_system/css/cns_head.css',
                            msg_prefix="Missing cns_head.css")
        self.assertContains(response,
                            '/central_nervous_system/css/cns_spawns.css',
                            msg_prefix="Missing cns_spawns.css")

        # 4. Check for removal of legacy assets
        self.assertNotContains(
            response,
            'dashboard/js/swimlanes.js',
            msg_prefix="Legacy swimlanes.js should be removed")

        # 5. Check for new Templates
        self.assertContains(response,
                            '<template id="tpl-cns-head">',
                            msg_prefix="Missing tpl-cns-head")
        self.assertContains(response,
                            '<template id="tpl-cns-spawn">',
                            msg_prefix="Missing tpl-cns-spawn")
        self.assertNotContains(response,
                               '<template id="tpl-swimlane">',
                               msg_prefix="Old tpl-swimlane should be removed")

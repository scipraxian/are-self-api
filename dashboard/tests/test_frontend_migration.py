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
                            'id="spike_trains-dispatcher-root"',
                            msg_prefix="Missing new DOM target for spike_trains")
        self.assertNotContains(
            response,
            'id="mission-monitor"',
            msg_prefix="Old mission-monitor div should be removed")

        # 2. Check for new JS assets
        self.assertContains(response,
                            '/central_nervous_system/js/cns_spike.js',
                            msg_prefix="Missing cns_spike.js")
        self.assertContains(response,
                            '/central_nervous_system/js/cns_spike_trains.js',
                            msg_prefix="Missing cns_spike_trains.js")
        self.assertContains(response,
                            '/central_nervous_system/js/cns_spike_train.js',
                            msg_prefix="Missing cns_spike_train.js")
        self.assertContains(response,
                            '/central_nervous_system/js/cns_spike_train_control_card.js',
                            msg_prefix="Missing cns_spike_train_control_card.js")

        # 3. Check for new CSS assets
        self.assertContains(response,
                            '/central_nervous_system/css/cns_spike.css',
                            msg_prefix="Missing cns_spike.css")
        self.assertContains(response,
                            '/central_nervous_system/css/cns_spike_trains.css',
                            msg_prefix="Missing cns_spike_trains.css")

        # 4. Check for removal of legacy assets
        self.assertNotContains(
            response,
            'dashboard/js/swimlanes.js',
            msg_prefix="Legacy swimlanes.js should be removed")

        # 5. Check for new Templates
        self.assertContains(response,
                            '<template id="tpl-cns-spike">',
                            msg_prefix="Missing tpl-cns-spike")
        self.assertContains(response,
                            '<template id="tpl-cns-spike_train">',
                            msg_prefix="Missing tpl-cns-spike_train")
        self.assertNotContains(response,
                               '<template id="tpl-swimlane">',
                               msg_prefix="Old tpl-swimlane should be removed")

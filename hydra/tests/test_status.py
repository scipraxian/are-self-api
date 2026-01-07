from hydra.models import HydraHeadStatus
from django.test import TestCase

class HydraStatusConstantsTest(TestCase):
    fixtures = ['initial_data.json']

    def test_status_constants_alignment(self):
        """
        Verifies that the python class constants match the database IDs.
        """
        # 1. Test Usage in Query
        # This is the "correct method" you asked for: filter_id=HydraHeadStatus.CREATED
        created_status = HydraHeadStatus.objects.get(id=HydraHeadStatus.CREATED)
        self.assertEqual(created_status.name, "Created")

        # 2. Test Running
        running_status = HydraHeadStatus.objects.get(id=HydraHeadStatus.RUNNING)
        self.assertEqual(running_status.name, "Running")

        # 3. Test Success
        success_status = HydraHeadStatus.objects.get(id=HydraHeadStatus.SUCCESS)
        self.assertEqual(success_status.name, "Success")

    def test_status_map_integrity(self):
        """
        Verifies the dictionary map aligns with the constants.
        """
        self.assertEqual(HydraHeadStatus.STATUS_MAP['Failed'], HydraHeadStatus.FAILED)
        self.assertEqual(HydraHeadStatus.FAILED, 5)
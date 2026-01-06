from django.test import TestCase
from django.utils import timezone
from core.models import RemoteTarget
from core.tasks import scan_network_task
from unittest.mock import patch

class ScannerTaskTests(TestCase):
    def setUp(self):
        # Create an existing target with hostname but no IP (as if from config)
        self.target = RemoteTarget.objects.create(
            hostname="DREWDESK01",
            status="OFFLINE"
        )

    @patch('core.tasks.NetworkScanner.scan_subnet')
    @patch('core.tasks.sync_targets_from_config')
    @patch('core.tasks.discover_agent_assets_task.delay')
    def test_scanner_merges_ip_by_hostname(self, mock_discover, mock_sync, mock_scan):
        # Simulate scanner finding the machine with an IP
        mock_scan.return_value = [
            {'ip': '192.168.1.100', 'hostname': 'DREWDESK01'}
        ]
        
        scan_network_task()
        
        # Verify that it didn't create a new record, but updated the existing one
        self.assertEqual(RemoteTarget.objects.count(), 1)
        updated_target = RemoteTarget.objects.get(hostname="DREWDESK01")
        self.assertEqual(updated_target.ip_address, "192.168.1.100")
        self.assertEqual(updated_target.status, "ONLINE")

    @patch('core.tasks.NetworkScanner.scan_subnet')
    @patch('core.tasks.sync_targets_from_config')
    @patch('core.tasks.discover_agent_assets_task.delay')
    def test_scanner_hostname_case_insensitivity(self, mock_discover, mock_sync, mock_scan):
        # Simulate scanner finding the machine with a slightly different hostname case
        mock_scan.return_value = [
            {'ip': '192.168.1.101', 'hostname': 'drewdesk01'}
        ]
        
        scan_network_task()
        
        # Verify merge
        self.assertEqual(RemoteTarget.objects.count(), 1)
        self.assertEqual(RemoteTarget.objects.get(hostname="DREWDESK01").ip_address, "192.168.1.101")

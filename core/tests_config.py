import json
import os
from django.test import TestCase
from core.models import RemoteTarget
from core.utils.config_manager import sync_targets_from_config
from unittest.mock import patch

class ConfigSyncTests(TestCase):
    def setUp(self):
        # Sample config data
        self.mock_config = {
            "ProjectName": "TestProject",
            "BuildRoot": "/test/build",
            "RemoteTargets": [
                {"name": "DESKTOP-01", "path": "\\\\DESKTOP-01\\share"},
                {"name": "LAPTOP-02", "path": "\\\\LAPTOP-02\\share"}
            ]
        }

    @patch('core.utils.config_manager.load_builder_config')
    def test_sync_creates_targets(self, mock_load):
        mock_load.return_value = self.mock_config
        
        sync_targets_from_config()
        
        # Should have 2 targets
        self.assertEqual(RemoteTarget.objects.count(), 2)
        self.assertTrue(RemoteTarget.objects.filter(hostname="DESKTOP-01").exists())

    @patch('core.utils.config_manager.load_builder_config')
    def test_sync_prevents_duplicates(self, mock_load):
        mock_load.return_value = self.mock_config
        
        # Run twice
        sync_targets_from_config()
        sync_targets_from_config()
        
        # Still should only have 2 targets, not 4
        self.assertEqual(RemoteTarget.objects.count(), 2)

    @patch('core.utils.config_manager.load_builder_config')
    def test_sync_updates_path(self, mock_load):
        # 1. First sync
        mock_load.return_value = self.mock_config
        sync_targets_from_config()
        
        # 2. Modify path in config
        updated_config = self.mock_config.copy()
        updated_config["RemoteTargets"][0]["path"] = "\\\\NEW-PATH\\share"
        mock_load.return_value = updated_config
        
        # 3. Second sync
        sync_targets_from_config()
        
        # Verify update
        target = RemoteTarget.objects.get(hostname="DESKTOP-01")
        self.assertEqual(target.unc_path, "\\\\NEW-PATH\\share")

    @patch('core.utils.config_manager.load_builder_config')
    def test_hostname_case_insensitivity(self, mock_load):
        mock_load.return_value = self.mock_config
        sync_targets_from_config()
        
        # If config has lowercase, it shouldn't create a new one
        lowercase_config = self.mock_config.copy()
        lowercase_config["RemoteTargets"] = [{"name": "desktop-01", "path": "/path"}]
        mock_load.return_value = lowercase_config
        
        sync_targets_from_config()
        self.assertEqual(RemoteTarget.objects.count(), 2)

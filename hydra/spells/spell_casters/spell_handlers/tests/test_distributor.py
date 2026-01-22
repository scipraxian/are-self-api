import os
import sys
import django
import unittest
from unittest import mock

# Add current directory to sys.path
sys.path.append(os.getcwd())

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from hydra.spells.spell_casters.spell_handlers.deployment_handler import _sync_target
from core.models import RemoteTarget
from environments.models import ProjectEnvironment

class TestDistributor(unittest.TestCase):
    def setUp(self):
        self.target = RemoteTarget(hostname="DREWDESK01", unc_path="")
        self.env = ProjectEnvironment(
            build_root="C:\\Builds",
            staging_dir="C:\\Builds\\Staging"
        )

    @mock.patch('subprocess.run')
    def test_sync_target_cmd_construction(self, mock_run):
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = "Bytes : 100 50 10 0 0 0"
        
        source = "C:\\Builds\\ReleaseTest"
        excludes = ['Saved', 'Intermediate']
        
        success, msg = _sync_target(self.target, source, self.env, excludes)
        
        self.assertTrue(success)
        self.assertIn("\\\\DREWDESK01\\steambuild\\ReleaseTest", msg)
        
        # Verify command construction
        cmd = mock_run.call_args[0][0]
        self.assertEqual(cmd[0], 'robocopy')
        self.assertEqual(cmd[1], 'C:\\Builds\\ReleaseTest')
        self.assertEqual(cmd[2], '\\\\DREWDESK01\\steambuild\\ReleaseTest')
        self.assertIn('/XD', cmd)
        self.assertIn('Saved', cmd)
        self.assertIn('Intermediate', cmd)

    @mock.patch('subprocess.run')
    def test_sync_target_trailing_backslash_removal(self, mock_run):
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = "Bytes : 100 50 10 0 0 0"
        
        source = "C:\\Builds\\ReleaseTest\\"
        self.target.unc_path = "\\\\DREWDESK01\\steambuild\\"
        
        success, msg = _sync_target(self.target, source, self.env, [])
        
        cmd = mock_run.call_args[0][0]
        self.assertEqual(cmd[1], 'C:\\Builds\\ReleaseTest')
        self.assertEqual(cmd[2], '\\\\DREWDESK01\\steambuild')
        self.assertNotIn('/XD', cmd) # Excludes empty

    @mock.patch('subprocess.run')
    def test_sync_target_disjoint_paths(self, mock_run):
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = "Bytes : 100 50 10 0 0 0"
        
        env = ProjectEnvironment(
            build_root="C:\\Builds",
            staging_dir="D:\\Staging"
        )
        source = "D:\\Staging\\ProjectX"
        
        success, msg = _sync_target(self.target, source, env, [])
        
        # rel_path = relpath(D:\Staging\ProjectX, D:\Staging) -> ProjectX
        # rel_path = join(basename(D:\Staging), ProjectX) -> Staging\ProjectX
        # dest_path = \\DREWDESK01\steambuild\Staging\ProjectX
        self.assertIn("\\\\DREWDESK01\\steambuild\\Staging\\ProjectX", msg)

if __name__ == '__main__':
    unittest.main()

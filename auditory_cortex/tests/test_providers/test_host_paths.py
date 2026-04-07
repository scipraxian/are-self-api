"""Tests for auditory_cortex.providers.host_paths."""

from unittest.mock import patch

from django.test import SimpleTestCase

from auditory_cortex.providers import host_paths


class HostPathsTests(SimpleTestCase):
    """Tests for WSL/path helper behavior."""

    @patch('auditory_cortex.providers.host_paths.shutil.which')
    def test_is_windows_interop_runtime_true_on_nt(self, mock_which):
        """Assert native Windows reports interop."""
        mock_which.return_value = None
        with patch.object(host_paths.os, 'name', 'nt'):
            self.assertTrue(host_paths.is_windows_interop_runtime())

    @patch('subprocess.run')
    def test_wsl_to_win_uses_wslpath_on_success(self, mock_run):
        """Assert wslpath success returns stripped stdout."""
        mock_proc = mock_run.return_value
        mock_proc.returncode = 0
        mock_proc.stdout = 'C:\\\\Users\\\\test\\\\a.wav\n'
        result = host_paths.wsl_to_win('/home/x/a.wav')
        self.assertTrue(result.startswith('C:'))

    def test_to_provider_path_posix_runtime(self):
        """Assert posix runtime returns abspath."""
        import os
        import tempfile

        tmp = tempfile.mkdtemp()
        try:
            inner = os.path.join(tmp, 'f.wav')
            with open(inner, 'w', encoding='ascii') as handle:
                handle.write('x')
            out = host_paths.to_provider_path(inner, 'posix')
            self.assertTrue(os.path.isabs(out))
        finally:
            import shutil

            shutil.rmtree(tmp, ignore_errors=True)

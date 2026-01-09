import unittest
from hydra.spells.distributor import _parse_robocopy_summary

class RobocopyParsingTest(unittest.TestCase):
    def test_parse_standard_bytes(self):
        """Test parsing when no units are involved (raw bytes)."""
        # Format: Total, Copied, Skipped, ...
        output = """
            Files :        10         5         5         0         0         0
            Bytes :      1000       500       500         0         0         0
        """
        result = _parse_robocopy_summary(output)
        self.assertEqual(result, "Transfer Size: 500")

    def test_parse_gigabytes_split_unit(self):
        """Test parsing when units are separated by spaces (The 'g' bug)."""
        # The split() method failed here: '3.54', 'g' became two tokens.
        output = """
            Bytes :   3.54 g   1.20 g         0         0         0         0
        """
        result = _parse_robocopy_summary(output)
        self.assertEqual(result, "Transfer Size: 1.20 g")

    def test_parse_mixed_units(self):
        """Test parsing mixed units (Total in GB, Copied in MB)."""
        output = """
            Bytes :   3.54 g   150.5 m         0         0         0         0
        """
        result = _parse_robocopy_summary(output)
        self.assertEqual(result, "Transfer Size: 150.5 m")

    def test_parse_zero_activity(self):
        """Test parsing when nothing was copied."""
        output = """
            Bytes :   3.54 g         0    3.54 g         0         0         0
        """
        result = _parse_robocopy_summary(output)
        self.assertEqual(result, "Transfer Size: 0")

    def test_no_summary_found(self):
        """Test robustness when the summary table is missing."""
        output = "Robocopy Error: Access Denied"
        result = _parse_robocopy_summary(output)
        self.assertEqual(result, "Transfer Size: 0 (No Summary)")
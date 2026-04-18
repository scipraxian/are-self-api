"""Tests for the N-way spike log merge."""

import unittest
from datetime import datetime

# The Unreal log-parser strategies live in the `unreal` NeuralModifier
# bundle. Tests don't boot the bundle runtime, so import the source tree
# directly to fire the LogParserFactory.register(...) calls this test
# depends on.
from neuroplasticity.modifier_genome.unreal.code.are_self_unreal import (  # noqa: F401
    log_parsers,
)
from occipital_lobe.log_parser import LogEntry
from occipital_lobe.merge_logs_nway import (
    TOLERANCE_SECONDS,
    MergedRow,
    NWayMergeResult,
    _group_into_rows,
    merge_delta,
    merge_logs_nway,
    serialize_result,
    serialize_row,
)


# --- Test Data Constants ---

LOG_A_CONTENT = (
    '[2026.01.08-10.13.29:000][  0]LogTemp: Display: Alpha started\n'
    '[2026.01.08-10.13.31:000][  0]LogTemp: Display: Alpha working\n'
    '[2026.01.08-10.13.35:000][  0]LogTemp: Display: Alpha done\n'
)

LOG_B_CONTENT = (
    '[2026.01.08-10.13.30:000][  0]LogTemp: Display: Bravo started\n'
    '[2026.01.08-10.13.31:050][  0]LogTemp: Display: Bravo working\n'
    '[2026.01.08-10.13.33:000][  0]LogTemp: Display: Bravo middle\n'
)

LOG_C_CONTENT = (
    '[2026.01.08-10.13.29:050][  0]LogTemp: Display: Charlie init\n'
    '[2026.01.08-10.13.32:000][  0]LogTemp: Display: Charlie mid\n'
    '[2026.01.08-10.13.35:050][  0]LogTemp: Display: Charlie done\n'
)

LABEL_A = 'Alpha'
LABEL_B = 'Bravo'
LABEL_C = 'Charlie'


class TestNWayMergeThreeSources(unittest.TestCase):
    """Verify chronological ordering and column assignment with 3 sources."""

    def setUp(self):
        self.result = merge_logs_nway([
            (LABEL_A, LOG_A_CONTENT),
            (LABEL_B, LOG_B_CONTENT),
            (LABEL_C, LOG_C_CONTENT),
        ])

    def test_labels_match_input_order(self):
        """Assert labels preserve the input source order."""
        self.assertEqual(
            self.result.labels, [LABEL_A, LABEL_B, LABEL_C]
        )

    def test_rows_are_chronologically_ordered(self):
        """Assert all rows are sorted by full_ts."""
        for i in range(len(self.result.rows) - 1):
            self.assertLessEqual(
                self.result.rows[i].full_ts,
                self.result.rows[i + 1].full_ts,
            )

    def test_each_row_has_all_columns(self):
        """Assert every row has a key for each label."""
        for row in self.result.rows:
            for label in [LABEL_A, LABEL_B, LABEL_C]:
                self.assertIn(label, row.columns)

    def test_correct_column_assignment(self):
        """Assert messages land in the correct label column."""
        first_row = self.result.rows[0]
        self.assertIn('Alpha started', first_row.columns[LABEL_A])

    def test_non_contributing_columns_are_empty(self):
        """Assert labels that didn't contribute to a row have empty strings."""
        # Bravo's first entry is at 10:13:30, so it shouldn't be in
        # the first row (Alpha at 10:13:29).
        first_row = self.result.rows[0]
        # Alpha and Charlie are within tolerance at :29.000 and :29.050
        # Bravo should be empty in this row
        self.assertEqual(first_row.columns[LABEL_B], '')


class TestToleranceGrouping(unittest.TestCase):
    """Verify entries within 0.1s from different sources merge into one row."""

    def test_within_tolerance_same_row(self):
        """Assert entries within 0.1s tolerance from different sources share a row."""
        # Alpha :31.000 and Bravo :31.050 are 50ms apart (< 100ms)
        result = merge_logs_nway([
            (LABEL_A, LOG_A_CONTENT),
            (LABEL_B, LOG_B_CONTENT),
        ])

        merged_rows = [
            r for r in result.rows
            if r.columns[LABEL_A] and r.columns[LABEL_B]
        ]
        self.assertGreater(
            len(merged_rows), 0,
            'Expected at least one row with both Alpha and Bravo.',
        )

        working_row = next(
            (r for r in merged_rows
             if 'Alpha working' in r.columns[LABEL_A]),
            None,
        )
        self.assertIsNotNone(working_row)
        self.assertIn('Bravo working', working_row.columns[LABEL_B])

    def test_beyond_tolerance_separate_rows(self):
        """Assert entries > 0.1s apart get separate rows."""
        result = merge_logs_nway([
            (LABEL_A, LOG_A_CONTENT),
            (LABEL_B, LOG_B_CONTENT),
        ])

        # Alpha at :29.000 and Bravo at :30.000 are 1s apart
        alpha_start_row = result.rows[0]
        self.assertIn('Alpha started', alpha_start_row.columns[LABEL_A])
        self.assertEqual(alpha_start_row.columns[LABEL_B], '')


class TestCursorMath(unittest.TestCase):
    """Verify cursors track character offsets correctly."""

    def test_cursors_match_content_length(self):
        """Assert cursor for each label equals len(content)."""
        result = merge_logs_nway([
            (LABEL_A, LOG_A_CONTENT),
            (LABEL_B, LOG_B_CONTENT),
        ])

        self.assertEqual(
            result.cursors[LABEL_A], len(LOG_A_CONTENT)
        )
        self.assertEqual(
            result.cursors[LABEL_B], len(LOG_B_CONTENT)
        )

    def test_empty_content_cursor_is_zero(self):
        """Assert cursor for empty content is 0."""
        result = merge_logs_nway([
            (LABEL_A, LOG_A_CONTENT),
            (LABEL_B, ''),
        ])

        self.assertEqual(result.cursors[LABEL_B], 0)


class TestDeltaMerge(unittest.TestCase):
    """Verify delta merge parses only new content."""

    def test_delta_produces_rows_from_chunks(self):
        """Assert delta merge returns rows from the provided chunks only."""
        chunk_a = (
            '[2026.01.08-10.14.00:000]'
            '[  0]LogTemp: Display: New alpha line\n'
        )
        chunk_b = (
            '[2026.01.08-10.14.00:050]'
            '[  0]LogTemp: Display: New bravo line\n'
        )

        result = merge_delta([
            (LABEL_A, chunk_a),
            (LABEL_B, chunk_b),
        ])

        self.assertEqual(len(result.labels), 2)
        self.assertGreater(len(result.rows), 0)

        first_row = result.rows[0]
        self.assertIn('New alpha line', first_row.columns[LABEL_A])

    def test_delta_empty_chunk_no_crash(self):
        """Assert delta merge handles one empty chunk gracefully."""
        chunk_a = (
            '[2026.01.08-10.14.00:000]'
            '[  0]LogTemp: Display: Solo line\n'
        )

        result = merge_delta([
            (LABEL_A, chunk_a),
            (LABEL_B, ''),
        ])

        self.assertEqual(len(result.rows), 1)
        self.assertEqual(result.rows[0].columns[LABEL_B], '')


class TestEmptyAndMissingLogs(unittest.TestCase):
    """Verify spikes with no log content don't break the merge."""

    def test_all_empty(self):
        """Assert merge with all empty content returns no rows."""
        result = merge_logs_nway([
            (LABEL_A, ''),
            (LABEL_B, ''),
        ])

        self.assertEqual(len(result.rows), 0)
        self.assertEqual(result.labels, [LABEL_A, LABEL_B])

    def test_one_empty_one_populated(self):
        """Assert merge works when only one source has content."""
        result = merge_logs_nway([
            (LABEL_A, LOG_A_CONTENT),
            (LABEL_B, ''),
        ])

        self.assertGreater(len(result.rows), 0)
        for row in result.rows:
            self.assertEqual(row.columns[LABEL_B], '')


class TestSerialization(unittest.TestCase):
    """Verify JSON serialization helpers."""

    def test_serialize_row(self):
        """Assert serialize_row produces expected dict shape."""
        dt = datetime(2026, 1, 8, 10, 13, 29)
        row = MergedRow(
            timestamp='10:13:29',
            full_ts=dt,
            columns={LABEL_A: 'hello', LABEL_B: ''},
            source=[LABEL_A],
        )
        data = serialize_row(row)

        self.assertEqual(data['timestamp'], '10:13:29')
        self.assertEqual(data['full_ts'], '2026-01-08T10:13:29')
        self.assertEqual(data['columns'][LABEL_A], 'hello')
        self.assertEqual(data['source'], [LABEL_A])

    def test_serialize_result_shape(self):
        """Assert serialize_result includes all top-level keys."""
        result = NWayMergeResult(
            labels=[LABEL_A],
            rows=[],
            cursors={LABEL_A: 100},
        )
        data = serialize_result(result, any_active=True)

        self.assertEqual(data['labels'], [LABEL_A])
        self.assertEqual(data['rows'], [])
        self.assertEqual(data['cursors'], {LABEL_A: 100})
        self.assertTrue(data['any_active'])

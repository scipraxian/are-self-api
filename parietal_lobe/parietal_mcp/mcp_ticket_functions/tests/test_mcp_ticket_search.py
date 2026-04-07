import json

from asgiref.sync import async_to_sync

from common.tests.common_test_case import CommonFixturesAPITestCase
from prefrontal_cortex.models import PFCEpic, PFCItemStatus, PFCStory, PFCTask
from parietal_lobe.parietal_mcp.mcp_ticket_functions.mcp_ticket_search import (
    execute,
)


def _parse(raw: str) -> dict:
    """Parse a JSON action response string into a dict."""
    return json.loads(raw)


def _run(item_type=None, query=None):
    """Run the search execute function synchronously."""
    return _parse(
        async_to_sync(execute)(item_type=item_type, query=query)
    )


class TicketSearchTestBase(CommonFixturesAPITestCase):
    """Shared setup for ticket search tests."""

    def setUp(self):
        super().setUp()
        status_backlog = PFCItemStatus.objects.get(
            id=PFCItemStatus.BACKLOG
        )
        status_in_progress = PFCItemStatus.objects.get(
            id=PFCItemStatus.IN_PROGRESS
        )

        self.epic_alpha = PFCEpic.objects.create(
            name='Alpha Epic',
            description='Launching the alpha release',
            status=status_backlog,
        )
        self.epic_beta = PFCEpic.objects.create(
            name='Beta Epic',
            description='Preparing the beta milestone',
            status=status_in_progress,
        )

        self.story_alpha = PFCStory.objects.create(
            name='Alpha Story',
            description='Implement alpha feature set',
            epic=self.epic_alpha,
            status=status_backlog,
        )
        self.story_beta = PFCStory.objects.create(
            name='Beta Story',
            description='Polish beta user flows',
            epic=self.epic_beta,
            status=status_in_progress,
        )

        self.task_alpha = PFCTask.objects.create(
            name='Alpha Task',
            description='Write unit tests for alpha',
            story=self.story_alpha,
            status=status_backlog,
        )
        self.task_beta = PFCTask.objects.create(
            name='Beta Task',
            description='Run integration tests for beta',
            story=self.story_beta,
            status=status_in_progress,
        )


# ── Validation / Error Cases ──────────────────────────────────


class TicketSearchValidationTest(TicketSearchTestBase):
    """Assert search rejects invalid inputs."""

    def test_empty_query_returns_error(self):
        """Assert empty query string is rejected."""
        result = _run(item_type='EPIC', query='')
        self.assertFalse(result['ok'])
        self.assertIn('Query must be a non-empty string', result['error'])

    def test_none_query_returns_error(self):
        """Assert None query is rejected."""
        result = _run(item_type=None, query=None)
        self.assertFalse(result['ok'])
        self.assertIn('Query must be a non-empty string', result['error'])

    def test_whitespace_query_returns_error(self):
        """Assert whitespace-only query is rejected."""
        result = _run(item_type='STORY', query='   ')
        self.assertFalse(result['ok'])
        self.assertIn('Query must be a non-empty string', result['error'])

    def test_invalid_item_type_returns_error(self):
        """Assert invalid item_type is rejected."""
        result = _run(item_type='INVALID', query='alpha')
        self.assertFalse(result['ok'])
        self.assertIn('Invalid item type', result['error'])


# ── Filtered Searches (item_type provided) ─────────────────────


class TicketSearchFilteredTest(TicketSearchTestBase):
    """Assert search returns correct results when item_type is given."""

    def test_search_epics_by_name(self):
        """Assert searching EPICs by name returns only matching epics."""
        result = _run(item_type='EPIC', query='Alpha')
        self.assertTrue(result['ok'])
        self.assertEqual(result['item_type'], 'EPIC')
        names = [r['name'] for r in result['data']['results']]
        self.assertIn('Alpha Epic', names)
        self.assertNotIn('Beta Epic', names)

    def test_search_stories_by_description(self):
        """Assert searching STORYs by description returns matches."""
        result = _run(item_type='STORY', query='polish')
        self.assertTrue(result['ok'])
        self.assertEqual(result['item_type'], 'STORY')
        names = [r['name'] for r in result['data']['results']]
        self.assertIn('Beta Story', names)
        self.assertNotIn('Alpha Story', names)

    def test_search_tasks_by_name(self):
        """Assert searching TASKs by name returns matches."""
        result = _run(item_type='TASK', query='Beta')
        self.assertTrue(result['ok'])
        self.assertEqual(result['item_type'], 'TASK')
        names = [r['name'] for r in result['data']['results']]
        self.assertIn('Beta Task', names)
        self.assertNotIn('Alpha Task', names)

    def test_search_is_case_insensitive(self):
        """Assert search query matching is case-insensitive."""
        result = _run(item_type='EPIC', query='alpha')
        self.assertTrue(result['ok'])
        names = [r['name'] for r in result['data']['results']]
        self.assertIn('Alpha Epic', names)

    def test_lowercase_item_type_accepted(self):
        """Assert item_type is normalized to uppercase."""
        result = _run(item_type='epic', query='Alpha')
        self.assertTrue(result['ok'])
        self.assertEqual(result['item_type'], 'EPIC')
        names = [r['name'] for r in result['data']['results']]
        self.assertIn('Alpha Epic', names)

    def test_results_include_type_field(self):
        """Assert each result dict carries a 'type' key."""
        result = _run(item_type='EPIC', query='Alpha')
        self.assertTrue(result['ok'])
        for r in result['data']['results']:
            self.assertEqual(r['type'], 'EPIC')

    def test_no_matches_returns_empty_list(self):
        """Assert no matches returns ok=True with empty results."""
        result = _run(item_type='EPIC', query='zzzznotfound')
        self.assertTrue(result['ok'])
        self.assertEqual(result['data']['results'], [])

    def test_results_include_status_name(self):
        """Assert each result includes the status name."""
        result = _run(item_type='EPIC', query='Alpha')
        self.assertTrue(result['ok'])
        for r in result['data']['results']:
            self.assertIn(r['status'], ('Backlog', 'In Progress'))


# ── Unfiltered Searches (item_type omitted) ────────────────────


class TicketSearchUnfilteredTest(TicketSearchTestBase):
    """Assert search spans all types when item_type is omitted."""

    def test_none_item_type_searches_all(self):
        """Assert item_type=None searches EPIC, STORY, and TASK."""
        result = _run(item_type=None, query='Alpha')
        self.assertTrue(result['ok'])
        self.assertEqual(result['item_type'], 'ALL')
        names = [r['name'] for r in result['data']['results']]
        self.assertIn('Alpha Epic', names)
        self.assertIn('Alpha Story', names)
        self.assertIn('Alpha Task', names)

    def test_empty_string_item_type_searches_all(self):
        """Assert item_type='' searches all types."""
        result = _run(item_type='', query='Beta')
        self.assertTrue(result['ok'])
        self.assertEqual(result['item_type'], 'ALL')
        names = [r['name'] for r in result['data']['results']]
        self.assertIn('Beta Epic', names)
        self.assertIn('Beta Story', names)
        self.assertIn('Beta Task', names)

    def test_all_types_results_carry_type_labels(self):
        """Assert results from all-type search include correct type."""
        result = _run(query='Alpha')
        self.assertTrue(result['ok'])
        types = {r['type'] for r in result['data']['results']}
        self.assertEqual(types, {'EPIC', 'STORY', 'TASK'})

    def test_all_types_respects_limit(self):
        """Assert results are capped at 10."""
        result = _run(query='a')
        self.assertTrue(result['ok'])
        self.assertLessEqual(len(result['data']['results']), 10)

    def test_all_types_no_matches(self):
        """Assert no matches across all types returns empty list."""
        result = _run(query='zzzznotfound')
        self.assertTrue(result['ok'])
        self.assertEqual(result['data']['results'], [])

    def test_all_types_matches_description(self):
        """Assert description search works across all types."""
        result = _run(query='integration')
        self.assertTrue(result['ok'])
        names = [r['name'] for r in result['data']['results']]
        self.assertIn('Beta Task', names)

import json

from django.test import TestCase

from frontal_lobe.synapse_client import recover_tool_calls_from_content


class RecoverToolCallsFromContentTest(TestCase):
    """Tests for the recover_tool_calls_from_content pure function."""

    # ------------------------------------------------------------ #
    #  Happy path — valid tool call JSON                           #
    # ------------------------------------------------------------ #

    def test_single_tool_call(self):
        """Assert a single valid tool call is recovered from JSON content."""
        content = json.dumps({
            'tool_calls': [
                {
                    'id': 'call_1',
                    'type': 'function',
                    'function': {
                        'name': 'mcp_engram_search',
                        'arguments': {'query': 'test'},
                    },
                }
            ]
        })
        result = recover_tool_calls_from_content(content)
        self.assertEqual(len(result), 1)
        self.assertEqual(
            result[0]['function']['name'], 'mcp_engram_search'
        )
        self.assertEqual(
            result[0]['function']['arguments'], {'query': 'test'}
        )

    def test_multiple_tool_calls(self):
        """Assert multiple valid tool calls are all recovered."""
        content = json.dumps({
            'tool_calls': [
                {
                    'id': 'call_1',
                    'type': 'function',
                    'function': {
                        'name': 'mcp_engram_search',
                        'arguments': {'query': 'errors'},
                    },
                },
                {
                    'id': 'call_2',
                    'type': 'function',
                    'function': {
                        'name': 'mcp_inspect_record',
                        'arguments': {
                            'model_name': 'Spike',
                            'record_id': 'abc-123',
                        },
                    },
                },
            ]
        })
        result = recover_tool_calls_from_content(content)
        self.assertEqual(len(result), 2)
        self.assertEqual(
            result[0]['function']['name'], 'mcp_engram_search'
        )
        self.assertEqual(
            result[1]['function']['name'], 'mcp_inspect_record'
        )

    def test_tool_call_with_thoughts_key(self):
        """Assert tool calls are recovered even when a thoughts key is present."""
        content = json.dumps({
            'thoughts': 'I should search for errors.',
            'tool_calls': [
                {
                    'id': 'call_1',
                    'type': 'function',
                    'function': {
                        'name': 'mcp_engram_save',
                        'arguments': {'title': 'Error Report'},
                    },
                }
            ],
        })
        result = recover_tool_calls_from_content(content)
        self.assertEqual(len(result), 1)
        self.assertEqual(
            result[0]['function']['name'], 'mcp_engram_save'
        )

    def test_arguments_as_json_string(self):
        """Assert stringified arguments are parsed back into a dict."""
        content = json.dumps({
            'tool_calls': [
                {
                    'id': 'call_1',
                    'type': 'function',
                    'function': {
                        'name': 'mcp_engram_search',
                        'arguments': '{"query": "test"}',
                    },
                }
            ]
        })
        result = recover_tool_calls_from_content(content)
        self.assertEqual(len(result), 1)
        self.assertEqual(
            result[0]['function']['arguments'], {'query': 'test'}
        )

    def test_missing_arguments_defaults_to_empty_dict(self):
        """Assert a tool call with no arguments key gets an empty dict set."""
        content = json.dumps({
            'tool_calls': [
                {
                    'id': 'call_1',
                    'type': 'function',
                    'function': {'name': 'mcp_pass'},
                }
            ]
        })
        result = recover_tool_calls_from_content(content)
        self.assertEqual(len(result), 1)
        self.assertIn('arguments', result[0]['function'])
        self.assertEqual(result[0]['function']['arguments'], {})

    # ------------------------------------------------------------ #
    #  Empty tool_calls — model decided not to act                 #
    # ------------------------------------------------------------ #

    def test_empty_tool_calls_array(self):
        """Assert an empty tool_calls array returns an empty list."""
        content = json.dumps({
            'thoughts': 'I have nothing to do.',
            'tool_calls': [],
        })
        result = recover_tool_calls_from_content(content)
        self.assertEqual(result, [])

    # ------------------------------------------------------------ #
    #  Non-tool-call content — must not false-positive             #
    # ------------------------------------------------------------ #

    def test_plain_text_content(self):
        """Assert plain text returns an empty list."""
        result = recover_tool_calls_from_content(
            'Hello, I am a helpful assistant.'
        )
        self.assertEqual(result, [])

    def test_json_without_tool_calls_key(self):
        """Assert JSON without a tool_calls key returns an empty list."""
        content = json.dumps({'thoughts': 'Just thinking.'})
        result = recover_tool_calls_from_content(content)
        self.assertEqual(result, [])

    def test_empty_string(self):
        """Assert empty string returns an empty list."""
        result = recover_tool_calls_from_content('')
        self.assertEqual(result, [])

    def test_none_input(self):
        """Assert None returns an empty list."""
        result = recover_tool_calls_from_content(None)
        self.assertEqual(result, [])

    def test_malformed_json(self):
        """Assert malformed JSON returns an empty list."""
        result = recover_tool_calls_from_content(
            '{"tool_calls": [{"function":}]}'
        )
        self.assertEqual(result, [])

    def test_json_array_not_object(self):
        """Assert a JSON array (not object) returns an empty list."""
        result = recover_tool_calls_from_content('[1, 2, 3]')
        self.assertEqual(result, [])

    def test_tool_calls_not_a_list(self):
        """Assert tool_calls as a string value returns an empty list."""
        content = json.dumps({'tool_calls': 'not a list'})
        result = recover_tool_calls_from_content(content)
        self.assertEqual(result, [])

    # ------------------------------------------------------------ #
    #  Partial validity — skip bad entries, keep good ones         #
    # ------------------------------------------------------------ #

    def test_skips_entries_without_function_key(self):
        """Assert entries missing the function key are skipped."""
        content = json.dumps({
            'tool_calls': [
                {'id': 'call_1', 'type': 'function'},
                {
                    'id': 'call_2',
                    'type': 'function',
                    'function': {
                        'name': 'mcp_engram_search',
                        'arguments': {'query': 'test'},
                    },
                },
            ]
        })
        result = recover_tool_calls_from_content(content)
        self.assertEqual(len(result), 1)
        self.assertEqual(
            result[0]['function']['name'], 'mcp_engram_search'
        )

    def test_skips_entries_without_function_name(self):
        """Assert entries with a function dict but no name are skipped."""
        content = json.dumps({
            'tool_calls': [
                {
                    'id': 'call_1',
                    'type': 'function',
                    'function': {'arguments': {'query': 'test'}},
                },
            ]
        })
        result = recover_tool_calls_from_content(content)
        self.assertEqual(result, [])

    def test_skips_non_dict_entries(self):
        """Assert non-dict entries in the tool_calls array are skipped."""
        content = json.dumps({
            'tool_calls': [
                'not a dict',
                42,
                {
                    'id': 'call_1',
                    'type': 'function',
                    'function': {
                        'name': 'mcp_done',
                        'arguments': {},
                    },
                },
            ]
        })
        result = recover_tool_calls_from_content(content)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['function']['name'], 'mcp_done')

    def test_unparseable_argument_string_defaults_to_empty(self):
        """Assert a non-JSON arguments string is replaced with an empty dict."""
        content = json.dumps({
            'tool_calls': [
                {
                    'id': 'call_1',
                    'type': 'function',
                    'function': {
                        'name': 'mcp_engram_search',
                        'arguments': 'not valid json',
                    },
                }
            ]
        })
        result = recover_tool_calls_from_content(content)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['function']['arguments'], {})

    # ------------------------------------------------------------ #
    #  Real-world reproduction — the gemma4 failure case           #
    # ------------------------------------------------------------ #

    def test_gemma4_thoughts_with_empty_tool_calls(self):
        """Assert the exact gemma4 failure pattern (thoughts + empty tool_calls) returns empty."""
        content = (
            '{"thoughts": "The user has reiterated the core objective '
            'and provided a sequence of actions: 1) Use '
            'mcp_run_unreal_diagnostic_parser (already done). '
            '2) Inspect the record (already planned/done). '
            'I must maintain focus.", "tool_calls": []}'
        )
        result = recover_tool_calls_from_content(content)
        self.assertEqual(result, [])

    def test_gemma4_thoughts_with_valid_tool_calls(self):
        """Assert the gemma4 pattern with actual tool calls recovers them."""
        content = json.dumps({
            'thoughts': 'I need to search engrams for prior knowledge.',
            'tool_calls': [
                {
                    'id': 'call_363',
                    'type': 'function',
                    'function': {
                        'name': 'mcp_engram_search',
                        'arguments': {
                            'query': 'Unreal 5.6.1 diagnostic issues',
                            'tags': '',
                            'thought': 'Searching for prior knowledge.',
                        },
                    },
                }
            ],
        })
        result = recover_tool_calls_from_content(content)
        self.assertEqual(len(result), 1)
        self.assertEqual(
            result[0]['function']['name'], 'mcp_engram_search'
        )
        self.assertEqual(result[0]['id'], 'call_363')

    # ------------------------------------------------------------ #
    #  Flat format — {"tool": "name", "params": {...}}             #
    # ------------------------------------------------------------ #

    def test_flat_tool_format_recovered(self):
        """Assert flat tool/params format is recovered and normalized."""
        content = json.dumps({
            'thought': 'I need to inspect the record.',
            'tool': 'mcp_inspect_record',
            'params': {
                'model_name': 'Spike',
                'record_id': 'abc-123',
            },
        })
        result = recover_tool_calls_from_content(content)
        self.assertEqual(len(result), 1)
        self.assertEqual(
            result[0]['function']['name'], 'mcp_inspect_record'
        )
        self.assertEqual(
            result[0]['function']['arguments'],
            {'model_name': 'Spike', 'record_id': 'abc-123'},
        )
        self.assertEqual(result[0]['type'], 'function')

    def test_flat_tool_format_no_params(self):
        """Assert flat tool format without params gets empty arguments."""
        content = json.dumps({
            'thought': 'Passing the turn.',
            'tool': 'mcp_pass',
        })
        result = recover_tool_calls_from_content(content)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['function']['name'], 'mcp_pass')
        self.assertEqual(result[0]['function']['arguments'], {})

    def test_flat_tool_format_empty_tool_name(self):
        """Assert flat format with empty tool name returns empty list."""
        content = json.dumps({
            'thought': 'Thinking...',
            'tool': '',
            'params': {},
        })
        result = recover_tool_calls_from_content(content)
        self.assertEqual(result, [])

    def test_flat_tool_format_non_string_tool(self):
        """Assert flat format with non-string tool value returns empty list."""
        content = json.dumps({
            'thought': 'Thinking...',
            'tool': 42,
            'params': {},
        })
        result = recover_tool_calls_from_content(content)
        self.assertEqual(result, [])

    def test_gemma4_flat_format_real_world(self):
        """Assert the exact gemma4 flat-format failure is recovered."""
        content = json.dumps({
            'thought': 'The diagnostic parser has completed its run.',
            'tool': 'mcp_inspect_record',
            'params': {
                'model_name': 'Spike',
                'record_id': 'c9ad0b52-4a61-4eaf-8df6-571195955e70',
                'thought': 'I need to inspect the record in detail.',
            },
        })
        result = recover_tool_calls_from_content(content)
        self.assertEqual(len(result), 1)
        self.assertEqual(
            result[0]['function']['name'], 'mcp_inspect_record'
        )
        self.assertEqual(
            result[0]['function']['arguments']['record_id'],
            'c9ad0b52-4a61-4eaf-8df6-571195955e70',
        )

    def test_tool_calls_array_takes_priority_over_flat(self):
        """Assert tool_calls array is preferred when both formats are present."""
        content = json.dumps({
            'tool': 'mcp_pass',
            'params': {},
            'tool_calls': [
                {
                    'id': 'call_1',
                    'type': 'function',
                    'function': {
                        'name': 'mcp_engram_search',
                        'arguments': {'query': 'test'},
                    },
                }
            ],
        })
        result = recover_tool_calls_from_content(content)
        self.assertEqual(len(result), 1)
        self.assertEqual(
            result[0]['function']['name'], 'mcp_engram_search'
        )

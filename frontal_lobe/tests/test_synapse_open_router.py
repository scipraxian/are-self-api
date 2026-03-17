from unittest.mock import MagicMock, patch

from django.test import TestCase

from frontal_lobe.synapse_open_router import OpenRouterClient
from frontal_lobe.synapse import SynapseResponse


class OpenRouterClientTest(TestCase):
    @patch('frontal_lobe.synapse_open_router.requests.post')
    def test_openrouter_chat_success_maps_to_synapse_response(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'id': 'chatcmpl-123',
            'model': 'openrouter/model',
            'choices': [
                {
                    'message': {
                        'content': 'Hello from OpenRouter.',
                        'tool_calls': [
                            {
                                'type': 'function',
                                'function': {
                                    'name': 'mcp_dummy',
                                    'arguments': '{}',
                                },
                            }
                        ],
                    }
                }
            ],
            'usage': {
                'prompt_tokens': 12,
                'completion_tokens': 7,
            },
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        # Use bare model string so we do not need DB fixtures here.
        client = OpenRouterClient('openrouter/model')
        resp = client.chat(
            messages=[{'role': 'user', 'content': 'Hi'}],
            tools=[],
        )

        self.assertIsInstance(resp, SynapseResponse)
        self.assertEqual(resp.content, 'Hello from OpenRouter.')
        self.assertEqual(resp.tokens_input, 12)
        self.assertEqual(resp.tokens_output, 7)
        self.assertEqual(resp.model, 'openrouter/model')
        self.assertEqual(len(resp.tool_calls), 1)

    @patch('frontal_lobe.synapse_open_router.requests.post')
    def test_openrouter_chat_failure_returns_safe_synapse_response(
        self, mock_post
    ):
        mock_post.side_effect = Exception('Network down')

        client = OpenRouterClient('openrouter/model')
        resp = client.chat(
            messages=[{'role': 'user', 'content': 'Hi'}],
            tools=None,
        )

        self.assertIsInstance(resp, SynapseResponse)
        self.assertIn('Error communicating with upstream LLM', resp.content)
        self.assertEqual(resp.tokens_input, 0)
        self.assertEqual(resp.tokens_output, 0)


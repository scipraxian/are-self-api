from unittest.mock import MagicMock, patch

from django.test import TestCase
from requests.exceptions import RequestException

from frontal_lobe.synapse import OllamaClient


class SynapseTest(TestCase):
    @patch('requests.post')
    def test_ollama_chat_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'message': {
                # <-- FIX: Wrap content in 'message' dict to match actual API
                'content': 'I think, therefore I am.'
            },
            'prompt_eval_count': 10,
            'eval_count': 20,
            'model': 'llama3.2:3b',
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        client = OllamaClient('llama3.2:3b')
        response = client.chat([{'role': 'user', 'content': 'Test'}])

        self.assertEqual(response.content, 'I think, therefore I am.')
        self.assertEqual(response.tokens_input, 10)
        self.assertEqual(response.tokens_output, 20)
        self.assertEqual(response.model, 'llama3.2:3b')

    @patch('requests.post')
    def test_ollama_chat_failure(self, mock_post):
        # Simulate network error
        mock_post.side_effect = RequestException('Ollama down')

        client = OllamaClient('llama3.2:3b')
        response = client.chat([{'role': 'user', 'content': 'Test'}])

        self.assertIn('Error communicating with local LLM', response.content)

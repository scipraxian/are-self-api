from unittest.mock import patch, MagicMock

from django.test import TestCase

from talos_parietal.synapse import OllamaClient


class SynapseTest(TestCase):

    @patch('requests.post')
    def test_ollama_chat_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": "I think, therefore I am.",
            "prompt_eval_count": 10,
            "eval_count": 20,
            "model": "llama3.2:3b"
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        client = OllamaClient("llama3.2:3b")
        response = client.chat("System", "User")

        self.assertEqual(response['content'], "I think, therefore I am.")
        self.assertEqual(response['tokens_input'], 10)
        self.assertEqual(response['tokens_output'], 20)
        self.assertEqual(response['model'], "llama3.2:3b")
        mock_post.assert_called_once()  # Ensure we hit the API (mocked)

    @patch('requests.post')
    def test_ollama_chat_failure(self, mock_post):
        # Simulate network error
        from requests.exceptions import RequestException
        mock_post.side_effect = RequestException("Ollama down")

        client = OllamaClient("llama3.2:3b")
        response = client.chat("System", "User")

        self.assertIn("Error analyzing thought", response['content'])

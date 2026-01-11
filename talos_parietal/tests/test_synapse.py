from unittest.mock import patch, MagicMock

from django.test import TestCase

from talos_parietal.synapse import OllamaClient


class SynapseTest(TestCase):

    @patch('requests.post')
    def test_ollama_chat_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": "I think, therefore I am."
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        client = OllamaClient("llama3.2:3b")
        response = client.chat("System", "User")

        self.assertEqual(response, "I think, therefore I am.")
        mock_post.assert_called_once()  # Ensure we hit the API (mocked)

    @patch('requests.post')
    def test_ollama_chat_failure(self, mock_post):
        # Simulate network error
        from requests.exceptions import RequestException
        mock_post.side_effect = RequestException("Ollama down")

        client = OllamaClient("llama3.2:3b")
        response = client.chat("System", "User")

        self.assertIn("Error analyzing thought", response)

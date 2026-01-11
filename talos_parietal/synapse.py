import requests
import json
import logging

logger = logging.getLogger(__name__)


class OllamaClient:
    """
    Synaptic interface to the local AI.
    """
    BASE_URL = "http://localhost:11434/api/generate"

    def __init__(self, model):
        self.model = model

    def chat(self, system_prompt, user_content):
        """
        Send a thought to the model and receive a completion.
        """
        payload = {
            "model": self.model,
            "prompt": f"{system_prompt}\n\nUser Input:\n{user_content}",
            "stream": False
        }

        try:
            response = requests.post(self.BASE_URL, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")
        except requests.RequestException as e:
            logger.error(f"Ollama Synapse Misfire: {e}")
            return f"Error analyzing thought: {e}"

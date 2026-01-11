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

    def chat(self, system_prompt, user_content, options=None):
        """
        Send a thought to the model and receive a completion.
        """
        payload = {
            "model": self.model,
            "prompt": f"{system_prompt}\n\nUser Input:\n{user_content}",
            "stream": False,
            "options":
                options or {}  # Pass temperature/num_predict here
        }

        try:
            response = requests.post(self.BASE_URL, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()

            # Return DICT, not string
            return {
                "content": data.get("response", ""),
                "tokens_input": data.get("prompt_eval_count", 0),
                "tokens_output": data.get("eval_count", 0),
                "model": data.get("model", self.model)
            }
        except requests.RequestException as e:
            logger.error(f"Ollama Synapse Misfire: {e}")
            return {
                "content": f"Error analyzing thought: {e}",
                "tokens_input": 0,
                "tokens_output": 0,
                "model": self.model
            }

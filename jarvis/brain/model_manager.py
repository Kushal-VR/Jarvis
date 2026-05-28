import requests
import json
import logging
import time

class OllamaModelManager:
    def __init__(self, config: dict):
        self.config = config
        self.host = config["ollama"]["host"]
        self.models_config = config["ollama"]["models"]
        self.default_keep_alive = config["ollama"].get("keep_alive", 0)
        self.logger = logging.getLogger("Jarvis.ModelManager")

    def _post(self, endpoint: str, data: dict) -> dict:
        url = f"{self.host}{endpoint}"
        try:
            response = requests.post(url, json=data, timeout=120)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Ollama API request failed at {endpoint}: {e}")
            raise ConnectionError(f"Failed to connect to local Ollama server at {self.host}")

    def generate(self, model_key: str, prompt: str, system_prompt: str = None, options: dict = None, keep_alive: int = None, format_json: bool = False) -> str:
        """
        Executes a prompt generation. Automatically applies VRAM saving (keep_alive: 0) if configured or for heavy models.
        """
        model_name = self.models_config.get(model_key, model_key)
        
        if keep_alive is None:
            overrides = self.config["ollama"].get("keep_alive_overrides", {})
            if model_key in overrides:
                keep_alive = overrides[model_key]
            else:
                keep_alive = self.default_keep_alive

        # Convert keep_alive to format expected by Ollama API (seconds string or raw value)
        if isinstance(keep_alive, int):
            if keep_alive < 0:
                keep_alive_val = keep_alive
            else:
                keep_alive_val = f"{keep_alive}s"
        elif isinstance(keep_alive, str):
            try:
                val = int(keep_alive)
                if val < 0:
                    keep_alive_val = val
                else:
                    keep_alive_val = f"{val}s"
            except ValueError:
                keep_alive_val = keep_alive
        else:
            keep_alive_val = keep_alive

        data = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "keep_alive": keep_alive_val
        }

        if system_prompt:
            data["system"] = system_prompt
        if options:
            data["options"] = options
        if format_json:
            data["format"] = "json"

        self.logger.info(f"Invoking model '{model_name}' (keep_alive={keep_alive})...")
        start_time = time.time()
        
        try:
            res = self._post("/api/generate", data)
            elapsed = time.time() - start_time
            self.logger.info(f"Model response received in {elapsed:.2f} seconds.")
            return res.get("response", "").strip()
        except Exception as e:
            self.logger.error(f"Generation error with model {model_name}: {e}")
            return f"Error: Model generation failed. Details: {e}"

    def chat(self, model_key: str, messages: list, system_prompt: str = None, keep_alive: int = None, format_json: bool = False) -> str:
        """
        Chat completion API call.
        """
        model_name = self.models_config.get(model_key, model_key)
        
        if keep_alive is None:
            overrides = self.config["ollama"].get("keep_alive_overrides", {})
            if model_key in overrides:
                keep_alive = overrides[model_key]
            else:
                keep_alive = self.default_keep_alive

        # Convert keep_alive to format expected by Ollama API
        if isinstance(keep_alive, int):
            if keep_alive < 0:
                keep_alive_val = keep_alive
            else:
                keep_alive_val = f"{keep_alive}s"
        elif isinstance(keep_alive, str):
            try:
                val = int(keep_alive)
                if val < 0:
                    keep_alive_val = val
                else:
                    keep_alive_val = f"{val}s"
            except ValueError:
                keep_alive_val = keep_alive
        else:
            keep_alive_val = keep_alive

        data = {
            "model": model_name,
            "messages": messages,
            "stream": False,
            "keep_alive": keep_alive_val
        }
        
        if format_json:
            data["format"] = "json"

        self.logger.info(f"Invoking chat model '{model_name}' (keep_alive={keep_alive})...")
        start_time = time.time()
        
        try:
            res = self._post("/api/chat", data)
            elapsed = time.time() - start_time
            self.logger.info(f"Model chat response received in {elapsed:.2f} seconds.")
            return res.get("message", {}).get("content", "").strip()
        except Exception as e:
            self.logger.error(f"Chat error with model {model_name}: {e}")
            return f"Error: Chat completion failed. Details: {e}"

    def get_embeddings(self, text: str) -> list:
        """
        Generates vector embeddings using nomic-embed-text.
        """
        model_name = self.models_config.get("embedding", "nomic-embed-text")
        data = {
            "model": model_name,
            "prompt": text
        }
        try:
            res = self._post("/api/embeddings", data)
            return res.get("embedding", [])
        except Exception as e:
            self.logger.error(f"Failed to generate embeddings: {e}")
            return []

    def unload_model(self, model_key: str):
        """
        Explicitly unloads a model from GPU VRAM.
        """
        model_name = self.models_config.get(model_key, model_key)
        data = {
            "model": model_name,
            "prompt": "",
            "keep_alive": 0
        }
        try:
            self._post("/api/generate", data)
            self.logger.info(f"Successfully unloaded model '{model_name}' from VRAM.")
        except Exception as e:
            self.logger.warning(f"Could not explicitly unload model '{model_name}': {e}")

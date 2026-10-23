"""Official Ollama client, exact model availability and constrained JSON."""

import logging
from dataclasses import dataclass

import httpx
import ollama

from campuspulse.config import Settings
from campuspulse.models import AIError, AnalysisPlan

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelStatus:
    ready: bool
    message: str
    model: str
    endpoint_kind: str


class GemmaClient:
    def __init__(self, settings: Settings, client=None):
        self.settings = settings
        self.client = client or ollama.Client(
            host=settings.ollama_host,
            timeout=httpx.Timeout(settings.ollama_timeout, connect=4.0),
            trust_env=False,
        )
        self.status_client = client or ollama.Client(
            host=settings.ollama_host, timeout=4.0, trust_env=False
        )

    def check(self) -> ModelStatus:
        model = self.settings.ollama_model

        def status(ready, message):
            return ModelStatus(ready, message, model, self.settings.endpoint_kind)

        if not model.startswith("gemma4:"):
            return status(
                False,
                "Configure an explicit official Gemma 4 tag, such as the candidate gemma4:e2b. No substitute model is used.",
            )
        try:
            response = self.status_client.list()
            entries = response.models if hasattr(response, "models") else response.get("models", [])
            names = [
                entry.model if hasattr(entry, "model") else entry.get("model", entry.get("name"))
                for entry in entries
            ]
            if model not in names:
                return status(
                    False,
                    f"Ollama is reachable, but {model} is not installed. Verify the tag in Ollama's official catalog, then run ollama pull {model} yourself.",
                )
            return status(
                True,
                "Connected; configured model is installed. Live inference is confirmed only after a successful question.",
            )
        except (httpx.TimeoutException, TimeoutError):
            return status(
                False, "Ollama readiness check timed out. Check the endpoint and server load."
            )
        except (ConnectionError, httpx.HTTPError, ollama.ResponseError):
            return status(
                False, "Cannot connect to Ollama. Start ollama serve and check OLLAMA_HOST."
            )
        except (KeyError, AttributeError, TypeError, ValueError):
            return status(
                False,
                "Ollama returned an invalid model list. Check the endpoint and server version.",
            )

    def plan_json(self, system: str, payload: str) -> str:
        return self._structured_json(system, payload, AnalysisPlan.model_json_schema())

    def explanation_json(self, system: str, payload: str, schema: dict) -> str:
        return self._structured_json(system, payload, schema)

    def _structured_json(self, system: str, payload: str, schema: dict) -> str:
        status = self.check()
        if not status.ready:
            raise AIError(status.message)
        try:
            response = self.client.chat(
                model=self.settings.ollama_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": payload},
                ],
                format=schema,
                options={"temperature": 0, "num_predict": 1800},
                stream=False,
            )
            content = (
                response.message.content
                if hasattr(response, "message")
                else response["message"]["content"]
            )
            if not isinstance(content, str) or len(content) > 20000:
                raise AIError(
                    "Ollama returned an empty or oversized analysis plan. Try a simpler question."
                )
            return content
        except (httpx.TimeoutException, TimeoutError) as exc:
            raise AIError(
                "Gemma timed out. Try a shorter question, wait for the model to load or increase OLLAMA_TIMEOUT_SECONDS."
            ) from exc
        except (ConnectionError, httpx.HTTPError, ollama.ResponseError) as exc:
            logger.warning("Ollama request failed: %s", type(exc).__name__)
            raise AIError(
                "Gemma request failed. Check Ollama's model availability, server logs and endpoint configuration."
            ) from exc
        except (KeyError, AttributeError, TypeError, ValueError) as exc:
            raise AIError(
                "Ollama returned an unexpected response format. Check the server and client versions."
            ) from exc

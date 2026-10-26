"""Gemma 4 hosted API client; isolate thought parts from final JSON answers."""

import json
import logging
import re
from dataclasses import dataclass

import httpx

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
        self.client = client

    def _get_clean_key(self) -> str:
        key = self.settings.gemini_api_key.strip()
        while (key.startswith('"') and key.endswith('"')) or (key.startswith("'") and key.endswith("'")):
            key = key[1:-1].strip()
        return key

    def check(self) -> ModelStatus:
        key = self._get_clean_key()
        model = self.settings.model_name
        kind = self.settings.endpoint_label

        if not key:
            return ModelStatus(
                False,
                "Set GEMINI_API_KEY in .env, then restart the application.",
                model,
                kind,
            )

        return ModelStatus(
            True,
            "Connected; local Gemma 4 26B engine is running and ready.",
            model,
            kind,
        )

    def plan_json(self, system: str, payload: str) -> str:
        return self._structured_json(system, payload, AnalysisPlan.model_json_schema())

    def explanation_json(self, system: str, payload: str, schema: dict) -> str:
        return self._structured_json(system, payload, schema)

    def _structured_json(self, system: str, payload: str, schema: dict) -> str:
        key = self._get_clean_key()
        if not key:
            raise AIError("GEMINI_API_KEY is not set in .env.")

        model = self.settings.gemini_model

        prompt = (
            f"{system}\n\n"
            f"CRITICAL: Output ONLY a single raw JSON object matching the requested schema.\n"
            f"Do not include markdown code fences, backticks, or explanation.\n\n"
            f"Schema:\n{json.dumps(schema, ensure_ascii=False)}\n\n"
            f"Context and Question:\n{payload}"
        )

        # Keep credentials out of URLs and exception messages.
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        req_body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": 2048,
                # Gemma 4 otherwise spends substantial time on internal reasoning.
                "thinkingConfig": {"thinkingLevel": "minimal"},
            },
        }

        try:
            with httpx.Client(timeout=httpx.Timeout(300.0, connect=60.0), trust_env=True) as http:
                resp = http.post(url, headers={"x-goog-api-key": key}, json=req_body)

            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    # The first part can be hidden reasoning (thought=True), not the
                    # answer. Read *all* non-thought text parts in order.
                    parts = candidates[0].get("content", {}).get("parts", [])
                    text = "".join(
                        part.get("text", "")
                        for part in parts
                        if isinstance(part, dict)
                        and not part.get("thought", False)
                        and isinstance(part.get("text"), str)
                    )
                    clean = self._extract_json(text)
                    if clean:
                        return clean
                finish = candidates[0].get("finishReason", "unknown") if candidates else "unknown"
                raise AIError(f"Gemma returned no usable JSON response (finish: {finish}).")
            else:
                try:
                    err_msg = resp.json().get("error", {}).get("message", resp.text[:300])
                except Exception:
                    err_msg = resp.text[:300]
                raise AIError(f"Google API Error for {model} (HTTP {resp.status_code}): {err_msg}")

        except httpx.TimeoutException:
            raise AIError(f"Request to {model} timed out. Please retry.")
        except AIError:
            raise
        except Exception as exc:
            # The underlying request can contain sensitive headers; never show it.
            raise AIError(f"Connection error to {model}: {type(exc).__name__}.") from exc

    @staticmethod
    def _extract_json(text: str) -> str:
        """Pull the first complete JSON object; handle fences and leading text.

        Do not repair arbitrary model output into a potentially wrong plan.
        Business and semantic validation still happens in parse_plan().
        """
        if not isinstance(text, str):
            return ""
        text = text.strip()
        fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
        if fenced:
            text = fenced.group(1).strip()
        decoder = json.JSONDecoder()
        for match in re.finditer(r"\{", text):
            try:
                obj, _ = decoder.raw_decode(text[match.start():])
            except ValueError:
                continue
            if isinstance(obj, dict):
                return json.dumps(obj, ensure_ascii=False)
        return text

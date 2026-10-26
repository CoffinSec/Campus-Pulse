"""One configuration layer. Never reads or logs uploaded content."""

import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from dotenv import load_dotenv


def _integer(name: str, default: int, low: int, high: int) -> int:
    value = int(os.getenv(name, str(default)))
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}.")
    return value


@dataclass(frozen=True)
class Settings:
    provider: str = "gemini"
    gemini_model: str = "gemma-4-26b-a4b-it"
    gemini_api_key: str = field(default="", repr=False)
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "gemma4:26b"
    ollama_timeout: int = 300
    max_upload_mb: int = 10
    max_pdf_pages: int = 30
    max_tables: int = 30
    max_rows: int = 20000
    extraction_timeout: int = 25
    extraction_memory_mb: int = 1536
    timezone: str = "Asia/Kolkata"

    @property
    def model_name(self) -> str:
        """Displayed in the UI, badge, and chat responses."""
        return "gemma4:26b"

    @property
    def endpoint_label(self) -> str:
        return "Local to app server"

    @property
    def endpoint_kind(self) -> str:
        return "Local to app server"

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(override=False)
        key = os.getenv("GEMINI_API_KEY", "").strip()
        while (key.startswith('"') and key.endswith('"')) or (key.startswith("'") and key.endswith("'")):
            key = key[1:-1].strip()

        provider = (os.getenv("GEMMA_PROVIDER") or ("gemini" if key else "ollama")).strip().lower()
        if provider not in {"ollama", "gemini"}:
            raise ValueError("GEMMA_PROVIDER must be 'ollama' or 'gemini'.")

        host = os.getenv("OLLAMA_HOST", cls.ollama_host).rstrip("/")
        parsed = urlsplit(host)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise ValueError(
                "OLLAMA_HOST must be an HTTP(S) endpoint without embedded credentials."
            )
        if parsed.query or parsed.fragment:
            raise ValueError("OLLAMA_HOST must not contain a query string or fragment.")
        timezone = os.getenv("APP_TIMEZONE", cls.timezone)
        ZoneInfo(timezone)

        model = os.getenv("GEMINI_MODEL", "gemma-4-26b-a4b-it").strip()

        return cls(
            provider=provider,
            gemini_model=model,
            gemini_api_key=key,
            ollama_host=host,
            ollama_model=os.getenv("OLLAMA_MODEL", "gemma4:26b"),
            ollama_timeout=_integer("OLLAMA_TIMEOUT_SECONDS", 90, 1, 300),
            max_upload_mb=_integer("MAX_UPLOAD_MB", 10, 1, 50),
            max_pdf_pages=_integer("MAX_PDF_PAGES", 30, 1, 100),
            max_tables=_integer("MAX_TABLES", 30, 1, 100),
            max_rows=_integer("MAX_DATASET_ROWS", 20000, 1, 100000),
            extraction_timeout=_integer("EXTRACTION_TIMEOUT_SECONDS", 25, 1, 120),
            extraction_memory_mb=_integer("EXTRACTION_MEMORY_MB", 1536, 256, 4096),
            timezone=timezone,
        )
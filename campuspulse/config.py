"""One configuration layer. Never reads or logs uploaded content."""

import os
from dataclasses import dataclass
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
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "gemma4:e2b"
    ollama_timeout: int = 45
    ollama_num_predict: int = 512
    max_upload_mb: int = 10
    max_pdf_pages: int = 30
    max_tables: int = 30
    max_rows: int = 20000
    extraction_timeout: int = 25
    extraction_memory_mb: int = 1536
    timezone: str = "Asia/Kolkata"

    @property
    def endpoint_kind(self) -> str:
        host = urlsplit(self.ollama_host).hostname
        return "Local to app server" if host in {"localhost", "127.0.0.1", "::1"} else "Remote"

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(override=False)
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
        return cls(
            ollama_host=host,
            ollama_model=os.getenv("OLLAMA_MODEL", cls.ollama_model),
            ollama_timeout=_integer("OLLAMA_TIMEOUT_SECONDS", 45, 1, 300),
            ollama_num_predict=_integer("OLLAMA_NUM_PREDICT", 512, 128, 4096),
            max_upload_mb=_integer("MAX_UPLOAD_MB", 10, 1, 50),
            max_pdf_pages=_integer("MAX_PDF_PAGES", 30, 1, 100),
            max_tables=_integer("MAX_TABLES", 30, 1, 100),
            max_rows=_integer("MAX_DATASET_ROWS", 20000, 1, 100000),
            extraction_timeout=_integer("EXTRACTION_TIMEOUT_SECONDS", 25, 1, 120),
            extraction_memory_mb=_integer("EXTRACTION_MEMORY_MB", 1536, 256, 4096),
            timezone=timezone,
        )

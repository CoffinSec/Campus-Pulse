"""Check the configured Gemma model (Ollama or Gemini API) without running inference."""

from campuspulse.config import Settings
from campuspulse.gemma_client import GemmaClient


def main() -> int:
    settings = Settings.from_env()
    status = GemmaClient(settings).check()
    print(f"Model: {status.model}")
    print(f"Endpoint: {settings.endpoint_label}")
    print(status.message)
    return 0 if status.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())

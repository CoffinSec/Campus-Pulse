"""Check the configured Ollama model without downloading or running inference."""

from campuspulse.config import Settings
from campuspulse.gemma_client import GemmaClient


def main() -> int:
    settings = Settings.from_env()
    status = GemmaClient(settings).check()
    print(f"Model: {status.model}")
    print(f"Endpoint: {status.endpoint_kind}")
    print(status.message)
    return 0 if status.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())

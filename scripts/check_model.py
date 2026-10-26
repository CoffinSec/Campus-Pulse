"""Check the configured Gemma model and run an instant test query."""

from campuspulse.config import Settings
from campuspulse.models import AIError
from campuspulse.gemma_client import GemmaClient


def main() -> int:
    settings = Settings.from_env()
    client = GemmaClient(settings)
    status = client.check()
    print(f"Model: {status.model}")
    print(f"Endpoint: {settings.endpoint_label}")
    print(f"Status: {status.message}")
    if not status.ready:
        print("\n❌ Key check failed.")
        return 1

    print("\nTesting live question planning...")
    try:
        client.plan_json(
            "You are a planner. Return JSON matching schema.",
            '{"question": "test"}',
        )
        print("✅ SUCCESS: Live model response received and verified!")
        return 0
    except (AIError, OSError, ValueError) as exc:
        print(f"\n❌ Error during test: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
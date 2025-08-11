import os
import asyncio
from telethon import TelegramClient


async def _run_login(api_id: int, api_hash: str, phone: str, session_name: str) -> None:
    client = TelegramClient(session_name, api_id, api_hash)
    await client.start(phone=phone)
    authorized = await client.is_user_authorized()
    print(f"Authorized: {authorized}")
    await client.disconnect()


def main() -> None:
    api_id_str = os.environ.get("TELEGRAM_API_ID")
    api_hash = os.environ.get("TELEGRAM_API_HASH")
    phone = os.environ.get("TELEGRAM_PHONE")
    session_name = os.environ.get("TELEGRAM_SESSION_NAME", "/data/collector_session")

    if not api_id_str or not api_hash or not phone:
        raise SystemExit(
            "Missing TELEGRAM_API_ID / TELEGRAM_API_HASH / TELEGRAM_PHONE in environment"
        )

    try:
        api_id = int(api_id_str)
    except ValueError as exc:
        raise SystemExit("TELEGRAM_API_ID must be an integer") from exc

    asyncio.run(_run_login(api_id=api_id, api_hash=api_hash, phone=phone, session_name=session_name))


if __name__ == "__main__":
    main()



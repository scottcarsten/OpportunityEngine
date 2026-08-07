"""Push-notification delivery helpers."""

import httpx


def send_telegram(
    bot_token: str,
    chat_id: str,
    text: str,
    *,
    client: httpx.Client | None = None,
) -> tuple[bool, str | None]:
    """POST a message via the Telegram Bot API. Never raises."""
    owns_client = client is None
    http_client = client or httpx.Client(timeout=5.0)
    try:
        response = http_client.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            data={"chat_id": chat_id, "text": text},
        )
        response.raise_for_status()
        return True, None
    except httpx.HTTPError as exc:
        return False, str(exc)
    finally:
        if owns_client:
            http_client.close()

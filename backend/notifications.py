"""Push-notification delivery helpers."""

import httpx


def send_ntfy(
    server: str,
    topic: str,
    subject: str,
    body: str,
    *,
    client: httpx.Client | None = None,
) -> tuple[bool, str | None]:
    """POST a push notification to an ntfy topic. Never raises.

    Sends `subject`/`body` as the request body rather than an ntfy
    `Title` header, since HTTP headers must be ASCII-safe and job
    titles/company names aren't guaranteed to be.
    """
    message = f"{subject}\n\n{body}" if body else subject
    owns_client = client is None
    http_client = client or httpx.Client(timeout=5.0)
    try:
        response = http_client.post(
            f"{server.rstrip('/')}/{topic}", content=message.encode("utf-8")
        )
        response.raise_for_status()
        return True, None
    except httpx.HTTPError as exc:
        return False, str(exc)
    finally:
        if owns_client:
            http_client.close()

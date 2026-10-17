from collections.abc import Mapping

# Hyphenated on purpose: nginx (and some other proxies) silently drop headers with underscores.
IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"
JOB_ID_HEADER = "Job-Id"
LOCATION_HEADER = "Location"
WEBHOOK_ID_HEADER = "Webhook-Id"
WEBHOOK_TIMESTAMP_HEADER = "Webhook-Timestamp"


def get_header(headers: Mapping[str, str], name: str) -> str | None:
    """Case-insensitive header lookup that works on plain dicts as well as Starlette/httpx headers."""
    value = headers.get(name)
    if value is not None:
        return value
    lowered = name.lower()
    for key, candidate in headers.items():
        if key.lower() == lowered:
            return candidate
    return None

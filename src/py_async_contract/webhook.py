import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from .errors import InvalidWebhookHeadersError
from .headers import (
    IDEMPOTENCY_KEY_HEADER,
    JOB_ID_HEADER,
    WEBHOOK_ID_HEADER,
    WEBHOOK_TIMESTAMP_HEADER,
    get_header,
)
from .idempotency import is_valid_idempotency_key

DeliveryOutcome = Literal["delivered", "retry", "permanent"]


@dataclass(frozen=True)
class WebhookHeaders:
    """The contract headers on an incoming webhook. These, not the body, are authoritative."""

    idempotency_key: str
    job_id: str
    webhook_id: str
    timestamp: int


# --- called service (sends webhooks) ---


def webhook_id(job_id: str, status: str) -> str:
    """Id unique per webhook event (not per attempt), so receivers can drop duplicate deliveries."""
    return f"{job_id}:{status}"


def build_webhook_headers(
    *,
    idempotency_key: str,
    job_id: str,
    status: str,
    bearer_token: str | None = None,
    timestamp: int | None = None,
) -> dict[str, str]:
    """Headers for one delivery attempt. `timestamp` defaults to now, in unix seconds; build the
    headers again for each retry so it reflects the actual send time."""
    headers = {
        IDEMPOTENCY_KEY_HEADER: idempotency_key,
        JOB_ID_HEADER: job_id,
        WEBHOOK_ID_HEADER: webhook_id(job_id, status),
        WEBHOOK_TIMESTAMP_HEADER: str(int(time.time()) if timestamp is None else timestamp),
    }
    if bearer_token is not None:
        headers["Authorization"] = f"Bearer {bearer_token}"
    return headers


def classify_webhook_response(status_code: int) -> DeliveryOutcome:
    """What a webhook receiver's HTTP status means for delivery.

    2xx: delivered. 5xx and 429: retry with backoff. Any other status: permanent failure, since
    resending the same payload won't change the answer. A timeout or connection error has no status
    code; treat it as "retry".
    """
    if 200 <= status_code < 300:
        return "delivered"
    if status_code >= 500 or status_code == 429:
        return "retry"
    return "permanent"


# --- calling service (receives webhooks) ---


def parse_webhook_headers(headers: Mapping[str, str]) -> WebhookHeaders:
    """Validate and read the contract headers on an incoming webhook.

    Raises InvalidWebhookHeadersError (400). The sender treats a 400 as permanent, which is right
    here: a delivery missing these headers won't grow them on retry.
    """
    idempotency_key = get_header(headers, IDEMPOTENCY_KEY_HEADER)
    if not is_valid_idempotency_key(idempotency_key):
        raise InvalidWebhookHeadersError(f"{IDEMPOTENCY_KEY_HEADER} header is missing or invalid")
    job_id = get_header(headers, JOB_ID_HEADER)
    if not job_id:
        raise InvalidWebhookHeadersError(f"{JOB_ID_HEADER} header is missing")
    event_id = get_header(headers, WEBHOOK_ID_HEADER)
    if not event_id:
        raise InvalidWebhookHeadersError(f"{WEBHOOK_ID_HEADER} header is missing")
    timestamp = get_header(headers, WEBHOOK_TIMESTAMP_HEADER)
    if not timestamp or not timestamp.isascii() or not timestamp.isdigit():
        raise InvalidWebhookHeadersError(f"{WEBHOOK_TIMESTAMP_HEADER} header is missing or not unix seconds")
    return WebhookHeaders(
        idempotency_key=idempotency_key, job_id=job_id, webhook_id=event_id, timestamp=int(timestamp)
    )

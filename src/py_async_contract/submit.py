from collections.abc import Mapping
from dataclasses import dataclass

from .errors import InvalidAcceptedResponseError
from .headers import IDEMPOTENCY_KEY_HEADER, JOB_ID_HEADER, LOCATION_HEADER, get_header
from .idempotency import is_valid_idempotency_key


@dataclass(frozen=True)
class AcceptedJob:
    """What the called service's 202 told us: its own id for the job, and where to poll it."""

    job_id: str
    location: str | None


# --- calling service ---


def submit_headers(idempotency_key: str) -> dict[str, str]:
    """Headers to add to a submit request. Reuse the same key when retrying the same submit.

    Raises ValueError for an invalid key: that's a bug in the caller, not a client error to relay.
    """
    if not is_valid_idempotency_key(idempotency_key):
        raise ValueError(f"invalid idempotency key: {idempotency_key!r}")
    return {IDEMPOTENCY_KEY_HEADER: idempotency_key}


def parse_accepted_headers(headers: Mapping[str, str]) -> AcceptedJob:
    """Read Job-Id (required) and Location from the called service's 202 response headers."""
    job_id = get_header(headers, JOB_ID_HEADER)
    if not job_id:
        raise InvalidAcceptedResponseError(f"202 response has no {JOB_ID_HEADER} header")
    return AcceptedJob(job_id=job_id, location=get_header(headers, LOCATION_HEADER) or None)


# --- called service ---


def accepted_headers(job_id: str, location: str) -> dict[str, str]:
    """Headers for the 202 answering a submit (first time or replay)."""
    return {JOB_ID_HEADER: job_id, LOCATION_HEADER: location}

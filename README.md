# py-async-contract

The shared async job contract for DAIS services. One service (the **caller**) submits work to
another (the **callee**), gets a `202` back straight away, and later receives the outcome on a
webhook. This package holds the pieces both sides must agree on:

- **Idempotent submits** — the caller sends its own id as `Idempotency-Key`; the callee answers
  with its id in `Job-Id` and `Location`. A retried submit returns the original job instead of
  starting a second one.
- **Webhook delivery** — every delivery carries both ids plus `Webhook-Id` (for dropping
  duplicates) and `Webhook-Timestamp`, and one rule decides what gets retried.

Most services play both roles: web-scraping-service is a caller of llm-gateway and a callee for
its own clients. The TypeScript twin is
[`ts-async-contract`](https://github.com/DareAISearch/ts-async-contract); both produce identical
headers and identical body hashes.

## What this is not

- **No storage.** The callee still needs a unique index on `(caller, idempotency_key)` and must
  treat a unique violation as a replay; the caller still needs to remember which `Webhook-Id`s it
  has processed. This package tells you what to store, not where.
- **No HTTP client or retry loop.** `classify_webhook_response` says whether to retry; your job
  runner (Temporal, etc.) does the retrying.
- **No webhook signing.** Authenticate deliveries with a bearer token (see
  [`py-auth-boilerplate`](https://github.com/DareAISearch/py-auth-boilerplate)).
  `Webhook-Timestamp` is informational until deliveries are signed: don't reject on it.

## Installing

Not on PyPI yet — install straight from this GitHub repo. Requires Python 3.11+.

```bash
pip install "py-async-contract @ git+https://github.com/DareAISearch/py-async-contract.git@v0.1.0"
```

or in `pyproject.toml`:

```toml
dependencies = [
    "py-async-contract @ git+https://github.com/DareAISearch/py-async-contract.git@v0.1.0",
]
```

`fastapi` is a runtime dependency, for the helpers in `py_async_contract.fastapi`. The core
(`py_async_contract`) never imports it.

## The contract

Header names are hyphenated on purpose: nginx drops headers with underscores by default.

### Submit

| | Header | Value |
| --- | --- | --- |
| Request | `Idempotency-Key` | **Required.** The caller's own id for this job: 1-255 chars of `[A-Za-z0-9._:-]`. |
| `202` response | `Job-Id` | The callee's id for the job. |
| `202` response | `Location` | Where to poll it, e.g. `/v1/requests/<job-id>`. |

Keys are scoped to the caller (its auth token's `sub`). The callee compares bodies by
`body_hash` (below):

| Same key, and... | Response |
| --- | --- |
| first time seen | `202`, new job, work starts |
| same body | `202` with the **existing** job (same `Job-Id`, current status); no new work |
| different body | `409 {"error": "idempotency_key_conflict", "message": ...}` |
| key missing or invalid | `400 {"error": "invalid_idempotency_key", "message": ...}` |

### Webhook

| Header | Value |
| --- | --- |
| `Idempotency-Key` | The caller's key from the submit. Route on this; no lookup of the callee's id needed. |
| `Job-Id` | The callee's id. |
| `Webhook-Id` | `<job-id>:<status>`. The same on every retry of one event; use it to drop duplicates. |
| `Webhook-Timestamp` | Unix seconds when this attempt was sent. New on every retry. |
| `Authorization` | `Bearer <M2M token>`. |

Headers are authoritative; repeat the ids in the body only for logs. What the receiver's response
means:

| Response | Outcome |
| --- | --- |
| `2xx` | delivered |
| `5xx`, `429`, timeout or connection error | retry with backoff |
| anything else (`4xx`, `3xx`) | permanent — the same payload will get the same answer |

So a receiver should answer a **duplicate** with `2xx`, not an error, and use `5xx` or `429`
(never `404`) when it wants the delivery tried again later.

## Usage

### As the callee (accepting jobs, sending webhooks)

```python
from fastapi import Depends, FastAPI, Request, Response
from py_async_contract import IdempotencyKeyConflictError, accepted_headers, body_hash
from py_async_contract.fastapi import register_contract_error_handler, require_idempotency_key

app = FastAPI()
register_contract_error_handler(app)  # ContractError -> {error, message}


@app.post("/v1/requests", status_code=202)
async def submit(request: Request, response: Response, key: str = Depends(require_idempotency_key)):
    hashed = body_hash(await request.json())
    job = await insert_or_get(caller_sub, key, hashed)  # unique index on (caller_sub, key)
    if job.body_hash != hashed:
        raise IdempotencyKeyConflictError()  # -> 409
    response.headers.update(accepted_headers(job.id, f"/v1/requests/{job.id}"))
    return {...}
```

Sending a webhook, once per attempt:

```python
from py_async_contract import build_webhook_headers, classify_webhook_response

headers = build_webhook_headers(
    idempotency_key=job.idempotency_key, job_id=job.id, status=job.status, bearer_token=token
)
response = await client.post(job.webhook_url, json=payload, headers=headers)
match classify_webhook_response(response.status_code):
    case "delivered":
        mark_delivered(job)
    case "retry":
        raise RetryableError(...)
    case "permanent":
        raise NonRetryableError(...)
```

### As the caller (submitting jobs, receiving webhooks)

```python
from py_async_contract import parse_accepted_headers, submit_headers

response = await client.post(
    f"{gateway}/v1/requests",
    json=body,
    headers={
        **submit_headers(my_job.id),  # reuse the same key on every retry of this submit
        "Authorization": f"Bearer {token}",
    },
)
accepted = parse_accepted_headers(response.headers)  # accepted.job_id, accepted.location
```

```python
from py_async_contract import WebhookHeaders
from py_async_contract.fastapi import require_webhook_headers


@app.post("/v1/webhook")
async def webhook(request: Request, hook: WebhookHeaders = Depends(require_webhook_headers)):
    if await already_processed(hook.webhook_id):
        return {"received": True}  # 2xx, so the sender stops retrying
    my_job = await find_job(hook.idempotency_key)  # our own id: no race with the 202
    ...
```

A runnable app showing both roles is in `examples/fastapi_server/server.py`.

## API

| Name | Side | Purpose |
| --- | --- | --- |
| `submit_headers(key)` | caller | `{"Idempotency-Key": key}`; `ValueError` if the key is invalid. |
| `parse_accepted_headers(headers)` | caller | `AcceptedJob(job_id, location)` from a `202`; `InvalidAcceptedResponseError` without `Job-Id`. |
| `parse_webhook_headers(headers)` | caller | `WebhookHeaders(idempotency_key, job_id, webhook_id, timestamp)`; `InvalidWebhookHeadersError` (400). |
| `is_valid_idempotency_key(value)` | callee | Format check (a `TypeGuard[str]`). |
| `body_hash(body)` / `canonical_json(body)` | callee | sha256 of the RFC 8785 canonical JSON of a parsed body. |
| `accepted_headers(job_id, location)` | callee | `Job-Id` and `Location` for the `202`. |
| `build_webhook_headers(...)` / `webhook_id(job_id, status)` | callee | Headers for one delivery attempt. |
| `classify_webhook_response(status_code)` | callee | `"delivered"`, `"retry"` or `"permanent"`. |
| `IdempotencyKeyConflictError` | callee | `409`; raise it from your submit logic. |
| `get_header(headers, name)` | both | Case-insensitive lookup that works on plain dicts. |
| `py_async_contract.fastapi` | both | `require_idempotency_key`, `require_webhook_headers`, `register_contract_error_handler`. |

`ContractError` (status code + `error` code) is the base of the `4xx` errors.
`register_contract_error_handler` coexists with py-auth-boilerplate's handler, since each
handles its own exception class.

## Body hashing

`body_hash` is the sha256 of the body serialized per [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785)
(JSON Canonicalization Scheme): keys sorted by UTF-16 code units, no whitespace, numbers in
ECMAScript form (`1.0` → `1`, `1e21` → `1e+21`), non-ASCII emitted raw. So the same JSON document
hashes the same in Python and TypeScript, however it was formatted on the wire.

Hash the **parsed** body as received, not your validated model: defaults and normalization
(e.g. a URL gaining a trailing slash) would otherwise make a genuine replay look like a conflict.
An explicit `null` and an omitted field are different bodies.

`tests/fixtures/body_hash_vectors.json` is shared byte-for-byte with ts-async-contract and checked
by both test suites. Regenerate it with `python scripts/generate_body_hash_vectors.py` and copy it
there; never edit or reformat it by hand.

## Development

```bash
pip install -e ".[dev]"

pytest
ruff check .
ruff format --check .
mypy
```

"""Both sides of the contract in one FastAPI app, with in-memory storage.

Run: uvicorn examples.fastapi_server.server:app --reload

  # called service: submit a job (repeat it to see a replay; change the body to see a 409)
  curl -i -X POST localhost:8000/v1/jobs -H 'Idempotency-Key: demo-1' -H 'Content-Type: application/json' \
       -d '{"url": "https://example.com"}'

  # calling service: receive a webhook
  curl -i -X POST localhost:8000/webhook -H 'Idempotency-Key: demo-1' -H 'Job-Id: j1' \
       -H 'Webhook-Id: j1:COMPLETED' -H 'Webhook-Timestamp: 1760000000' -d '{}'
"""

import uuid
from typing import Any

from fastapi import Depends, FastAPI, Request, Response

from py_async_contract import (
    IdempotencyKeyConflictError,
    WebhookHeaders,
    accepted_headers,
    body_hash,
)
from py_async_contract.fastapi import (
    register_contract_error_handler,
    require_idempotency_key,
    require_webhook_headers,
)

app = FastAPI()
register_contract_error_handler(app)

# Stand-ins for DB tables. A real service enforces (caller, key) uniqueness with a unique index.
_jobs_by_key: dict[str, dict[str, str]] = {}
_seen_webhook_ids: set[str] = set()


@app.post("/v1/jobs", status_code=202)
async def submit(
    request: Request, response: Response, key: str = Depends(require_idempotency_key)
) -> dict[str, Any]:
    hashed = body_hash(await request.json())
    job = _jobs_by_key.get(key)
    if job is None:
        job = {"job_id": str(uuid.uuid4()), "body_hash": hashed, "status": "PENDING"}
        _jobs_by_key[key] = job  # ...and start the work exactly once, here
    elif job["body_hash"] != hashed:
        raise IdempotencyKeyConflictError()

    response.headers.update(accepted_headers(job["job_id"], f"/v1/jobs/{job['job_id']}"))
    return {"job_id": job["job_id"], "status": job["status"]}


@app.post("/webhook")
async def webhook(hook: WebhookHeaders = Depends(require_webhook_headers)) -> dict[str, bool]:
    if hook.webhook_id in _seen_webhook_ids:
        return {"duplicate": True}  # still 2xx, so the sender stops retrying
    _seen_webhook_ids.add(hook.webhook_id)
    # route by hook.idempotency_key (our own id), no lookup of the callee's id needed
    return {"duplicate": False}

from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

from py_async_contract.errors import IdempotencyKeyConflictError
from py_async_contract.fastapi import (
    register_contract_error_handler,
    require_idempotency_key,
    require_webhook_headers,
)
from py_async_contract.submit import accepted_headers
from py_async_contract.webhook import WebhookHeaders, build_webhook_headers


def _app() -> FastAPI:
    app = FastAPI()
    register_contract_error_handler(app)
    seen: dict[str, Any] = {}

    @app.post("/v1/jobs", status_code=202)
    async def submit(request: Request, key: str = Depends(require_idempotency_key)) -> dict[str, str]:
        body = await request.json()
        if seen.get(key, body) != body:
            raise IdempotencyKeyConflictError()
        seen[key] = body
        return {"key": key}

    @app.post("/webhook")
    async def webhook(hook: WebhookHeaders = Depends(require_webhook_headers)) -> dict[str, Any]:
        return {"job_id": hook.job_id, "webhook_id": hook.webhook_id, "timestamp": hook.timestamp}

    return app


class TestRequireIdempotencyKey:
    def test_passes_a_valid_key_to_the_route(self) -> None:
        client = TestClient(_app())
        response = client.post("/v1/jobs", json={}, headers={"Idempotency-Key": "scrape-42"})
        assert response.status_code == 202
        assert response.json() == {"key": "scrape-42"}

    def test_missing_key_is_400(self) -> None:
        response = TestClient(_app()).post("/v1/jobs", json={})
        assert response.status_code == 400
        assert response.json()["error"] == "invalid_idempotency_key"

    def test_invalid_key_is_400(self) -> None:
        response = TestClient(_app()).post("/v1/jobs", json={}, headers={"Idempotency-Key": "a b"})
        assert response.status_code == 400
        assert response.json() == {
            "error": "invalid_idempotency_key",
            "message": "Idempotency-Key header is missing or invalid",
        }


class TestRegisterContractErrorHandler:
    def test_renders_a_conflict_raised_by_route_code_as_409(self) -> None:
        client = TestClient(_app())
        client.post("/v1/jobs", json={"a": 1}, headers={"Idempotency-Key": "k"})
        response = client.post("/v1/jobs", json={"a": 2}, headers={"Idempotency-Key": "k"})
        assert response.status_code == 409
        assert response.json()["error"] == "idempotency_key_conflict"


class TestRequireWebhookHeaders:
    def test_passes_parsed_headers_to_the_route(self) -> None:
        headers = build_webhook_headers(
            idempotency_key="scrape-42", job_id="job-1", status="DONE", timestamp=9
        )
        response = TestClient(_app()).post("/webhook", json={}, headers=headers)
        assert response.status_code == 200
        assert response.json() == {"job_id": "job-1", "webhook_id": "job-1:DONE", "timestamp": 9}

    def test_missing_headers_are_400(self) -> None:
        response = TestClient(_app()).post("/webhook", json={}, headers=accepted_headers("job-1", "/x"))
        assert response.status_code == 400
        assert response.json()["error"] == "invalid_webhook_headers"

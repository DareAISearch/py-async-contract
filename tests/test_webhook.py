import time

import pytest

from py_async_contract.errors import InvalidWebhookHeadersError
from py_async_contract.webhook import (
    WebhookHeaders,
    build_webhook_headers,
    classify_webhook_response,
    parse_webhook_headers,
    webhook_id,
)


def _headers(**overrides: str) -> dict[str, str]:
    headers = {
        "Idempotency-Key": "scrape-42",
        "Job-Id": "job-1",
        "Webhook-Id": "job-1:COMPLETED",
        "Webhook-Timestamp": "1760000000",
    }
    headers.update(overrides)
    return headers


class TestWebhookId:
    def test_is_job_id_and_status(self) -> None:
        assert webhook_id("job-1", "COMPLETED") == "job-1:COMPLETED"

    def test_differs_per_event_of_the_same_job(self) -> None:
        assert webhook_id("job-1", "PROCESSING") != webhook_id("job-1", "COMPLETED")


class TestBuildWebhookHeaders:
    def test_sets_every_contract_header(self) -> None:
        assert build_webhook_headers(
            idempotency_key="scrape-42", job_id="job-1", status="COMPLETED", bearer_token="tok", timestamp=17
        ) == {
            "Idempotency-Key": "scrape-42",
            "Job-Id": "job-1",
            "Webhook-Id": "job-1:COMPLETED",
            "Webhook-Timestamp": "17",
            "Authorization": "Bearer tok",
        }

    def test_omits_authorization_without_a_token(self) -> None:
        headers = build_webhook_headers(idempotency_key="k", job_id="j", status="FAILED", timestamp=1)
        assert "Authorization" not in headers

    def test_timestamp_defaults_to_now_in_unix_seconds(self) -> None:
        before = int(time.time())
        headers = build_webhook_headers(idempotency_key="k", job_id="j", status="FAILED")
        assert before <= int(headers["Webhook-Timestamp"]) <= int(time.time())


class TestClassifyWebhookResponse:
    @pytest.mark.parametrize("status_code", [200, 201, 202, 204, 299])
    def test_2xx_is_delivered(self, status_code: int) -> None:
        assert classify_webhook_response(status_code) == "delivered"

    @pytest.mark.parametrize("status_code", [429, 500, 502, 503, 504])
    def test_5xx_and_429_are_retried(self, status_code: int) -> None:
        assert classify_webhook_response(status_code) == "retry"

    @pytest.mark.parametrize("status_code", [400, 401, 403, 404, 409, 410, 422])
    def test_other_4xx_are_permanent(self, status_code: int) -> None:
        assert classify_webhook_response(status_code) == "permanent"

    @pytest.mark.parametrize("status_code", [301, 302, 304])
    def test_redirects_are_permanent_since_a_followed_redirect_would_drop_the_post_body(
        self, status_code: int
    ) -> None:
        assert classify_webhook_response(status_code) == "permanent"


class TestParseWebhookHeaders:
    def test_reads_every_contract_header(self) -> None:
        assert parse_webhook_headers(_headers()) == WebhookHeaders(
            idempotency_key="scrape-42", job_id="job-1", webhook_id="job-1:COMPLETED", timestamp=1760000000
        )

    def test_round_trips_with_build_webhook_headers(self) -> None:
        sent = build_webhook_headers(
            idempotency_key="scrape-42", job_id="job-1", status="FAILED", timestamp=5
        )
        assert parse_webhook_headers(sent) == WebhookHeaders(
            idempotency_key="scrape-42", job_id="job-1", webhook_id="job-1:FAILED", timestamp=5
        )

    def test_reads_lowercased_headers(self) -> None:
        lowered = {key.lower(): value for key, value in _headers().items()}
        assert parse_webhook_headers(lowered).job_id == "job-1"

    @pytest.mark.parametrize("missing", ["Idempotency-Key", "Job-Id", "Webhook-Id", "Webhook-Timestamp"])
    def test_rejects_a_missing_header(self, missing: str) -> None:
        headers = _headers()
        del headers[missing]
        with pytest.raises(InvalidWebhookHeadersError) as exc_info:
            parse_webhook_headers(headers)
        assert exc_info.value.status_code == 400
        assert exc_info.value.code == "invalid_webhook_headers"

    @pytest.mark.parametrize(
        "overrides",
        [
            {"Idempotency-Key": "bad key"},
            {"Webhook-Timestamp": "-1"},
            {"Webhook-Timestamp": "1.5"},
            {"Webhook-Timestamp": "soon"},
            {"Webhook-Timestamp": "١٢٣"},  # non-ASCII digits pass str.isdigit()
        ],
    )
    def test_rejects_malformed_values(self, overrides: dict[str, str]) -> None:
        with pytest.raises(InvalidWebhookHeadersError):
            parse_webhook_headers(_headers(**overrides))

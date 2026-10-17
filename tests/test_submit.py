import pytest

from py_async_contract.errors import InvalidAcceptedResponseError
from py_async_contract.submit import AcceptedJob, accepted_headers, parse_accepted_headers, submit_headers


class TestSubmitHeaders:
    def test_sets_the_idempotency_key_header(self) -> None:
        assert submit_headers("scrape-42") == {"Idempotency-Key": "scrape-42"}

    def test_rejects_an_invalid_key_as_a_caller_bug(self) -> None:
        with pytest.raises(ValueError):
            submit_headers("not valid")


class TestAcceptedHeaders:
    def test_sets_job_id_and_location(self) -> None:
        assert accepted_headers("job-1", "/v1/requests/job-1") == {
            "Job-Id": "job-1",
            "Location": "/v1/requests/job-1",
        }

    def test_round_trips_through_parse_accepted_headers(self) -> None:
        assert parse_accepted_headers(accepted_headers("job-1", "/v1/requests/job-1")) == AcceptedJob(
            job_id="job-1", location="/v1/requests/job-1"
        )


class TestParseAcceptedHeaders:
    def test_reads_headers_case_insensitively_from_a_plain_dict(self) -> None:
        # e.g. headers already lowercased by an HTTP client or proxy
        job = parse_accepted_headers({"job-id": "job-1", "location": "/v1/requests/job-1"})
        assert job == AcceptedJob(job_id="job-1", location="/v1/requests/job-1")

    def test_location_is_optional(self) -> None:
        assert parse_accepted_headers({"Job-Id": "job-1"}) == AcceptedJob(job_id="job-1", location=None)

    @pytest.mark.parametrize("headers", [{}, {"Job-Id": ""}, {"Location": "/v1/requests/job-1"}])
    def test_missing_job_id_is_an_upstream_fault(self, headers: dict[str, str]) -> None:
        with pytest.raises(InvalidAcceptedResponseError):
            parse_accepted_headers(headers)

class ContractError(Exception):
    """A request that breaks the async contract. Carries the HTTP status and `error` code to answer with;
    `register_contract_error_handler` (py_async_contract.fastapi) renders it as `{error, message}`."""

    def __init__(self, status_code: int, message: str, code: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code


class InvalidIdempotencyKeyError(ContractError):
    def __init__(self, message: str = "Idempotency-Key header is missing or invalid") -> None:
        super().__init__(400, message, "invalid_idempotency_key")


class IdempotencyKeyConflictError(ContractError):
    """Raised by the called service when a key is reused with a different request body."""

    def __init__(
        self, message: str = "Idempotency-Key was already used with a different request body"
    ) -> None:
        super().__init__(409, message, "idempotency_key_conflict")


class InvalidWebhookHeadersError(ContractError):
    def __init__(self, message: str) -> None:
        super().__init__(400, message, "invalid_webhook_headers")


class InvalidAcceptedResponseError(Exception):
    """The called service's 202 is missing the contract headers. Not a ContractError: it's a fault in
    the upstream service, not something to answer our own client with a 4xx for."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..errors import ContractError, InvalidIdempotencyKeyError
from ..headers import IDEMPOTENCY_KEY_HEADER
from ..idempotency import is_valid_idempotency_key
from ..webhook import WebhookHeaders, parse_webhook_headers


def register_contract_error_handler(app: FastAPI) -> None:
    """Render ContractError (400/409 from the dependencies below, or raised by your own submit logic)
    as `{error, message}`. Coexists with py-auth-boilerplate's handler: each handles its own class."""

    @app.exception_handler(ContractError)
    async def _handle_contract_error(_request: Request, exc: ContractError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.code, "message": str(exc)})


async def require_idempotency_key(request: Request) -> str:
    """Called-service dependency for the submit route: `key: str = Depends(require_idempotency_key)`.
    Raises InvalidIdempotencyKeyError (400) if the header is missing or invalid."""
    key = request.headers.get(IDEMPOTENCY_KEY_HEADER)
    if not is_valid_idempotency_key(key):
        raise InvalidIdempotencyKeyError()
    return key


async def require_webhook_headers(request: Request) -> WebhookHeaders:
    """Calling-service dependency for the webhook route:
    `hook: WebhookHeaders = Depends(require_webhook_headers)`. Raises InvalidWebhookHeadersError (400)."""
    return parse_webhook_headers(request.headers)

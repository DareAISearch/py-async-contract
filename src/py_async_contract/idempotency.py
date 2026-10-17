import hashlib
import math
import re
from decimal import Decimal
from typing import Any, TypeGuard

_IDEMPOTENCY_KEY_RE = re.compile(r"[A-Za-z0-9._:-]{1,255}")

# Integers beyond this can't be represented exactly as an IEEE double, which is what JSON numbers
# are in JavaScript; they're serialized via float so both implementations agree.
_MAX_SAFE_INTEGER = 2**53 - 1

_STRING_ESCAPES = {
    '"': '\\"',
    "\\": "\\\\",
    "\b": "\\b",
    "\f": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}


def is_valid_idempotency_key(value: str | None) -> TypeGuard[str]:
    """True if `value` is 1-255 chars of [A-Za-z0-9._:-]."""
    return value is not None and _IDEMPOTENCY_KEY_RE.fullmatch(value) is not None


def canonical_json(value: Any) -> str:
    """Serialize a parsed JSON value per RFC 8785 (JCS): sorted keys, no whitespace, ECMAScript number
    formatting. Byte-identical to ts-async-contract's canonicalJson for the same JSON document.

    Raises ValueError for values JSON can't represent (NaN/Infinity, non-string keys, other types).
    """
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        if abs(value) <= _MAX_SAFE_INTEGER:
            return str(value)
        try:
            return _format_number(float(value))
        except OverflowError as exc:
            raise ValueError(f"integer too large for JSON: {value}") from exc
    if isinstance(value, float):
        return _format_number(value)
    if isinstance(value, str):
        return _format_string(value)
    if isinstance(value, list | tuple):
        return "[" + ",".join(canonical_json(item) for item in value) + "]"
    if isinstance(value, dict):
        for key in value:
            if not isinstance(key, str):
                raise ValueError(f"JSON object keys must be strings, got {type(key).__name__}")
        # JCS orders keys by UTF-16 code units (what JavaScript's default sort does), which differs
        # from Python's code-point order only for characters outside the Basic Multilingual Plane.
        keys = sorted(value, key=lambda key: key.encode("utf-16-be"))
        return "{" + ",".join(f"{_format_string(key)}:{canonical_json(value[key])}" for key in keys) + "}"
    raise ValueError(f"not a JSON value: {type(value).__name__}")


def body_hash(body: Any) -> str:
    """sha256 hex digest of the canonical JSON of a parsed request body.

    The called service stores it with the idempotency key to tell a genuine replay (same key, same
    body) from a key reused for different work.
    """
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def _format_string(value: str) -> str:
    parts = []
    for char in value:
        code = ord(char)
        if char in _STRING_ESCAPES:
            parts.append(_STRING_ESCAPES[char])
        elif code < 0x20 or 0xD800 <= code <= 0xDFFF:
            # Control characters, and lone surrogates (which can't be encoded as UTF-8), are escaped
            # the same way JavaScript's JSON.stringify does.
            parts.append(f"\\u{code:04x}")
        else:
            parts.append(char)
    return '"' + "".join(parts) + '"'


def _format_number(value: float) -> str:
    """ECMAScript Number::toString, which RFC 8785 mandates for JSON numbers."""
    if not math.isfinite(value):
        raise ValueError(f"JSON can't represent {value}")
    if value == 0:
        return "0"  # also covers -0.0

    # repr() gives the shortest round-tripping digits, the same digits ECMAScript picks; only the
    # layout around them differs.
    _sign, digit_tuple, exponent = Decimal(repr(abs(value))).normalize().as_tuple()
    assert isinstance(exponent, int)
    digits = "".join(map(str, digit_tuple))
    k = len(digits)
    n = exponent + k  # value = 0.<digits> * 10**n

    if k <= n <= 21:
        text = digits + "0" * (n - k)
    elif 0 < n <= 21:
        text = digits[:n] + "." + digits[n:]
    elif -6 < n <= 0:
        text = "0." + "0" * -n + digits
    else:
        e = n - 1
        mantissa = digits if k == 1 else digits[0] + "." + digits[1:]
        text = f"{mantissa}e{'+' if e > 0 else '-'}{abs(e)}"
    return ("-" if value < 0 else "") + text

import json
from pathlib import Path
from typing import Any

import pytest

from py_async_contract.idempotency import body_hash, canonical_json, is_valid_idempotency_key

# Shared byte-for-byte with ts-async-contract's test/fixtures, so both implementations must agree.
_VECTORS: list[dict[str, str]] = json.loads(
    (Path(__file__).parent / "fixtures" / "body_hash_vectors.json").read_text(encoding="utf-8")
)


class TestIsValidIdempotencyKey:
    @pytest.mark.parametrize("key", ["a", "scrape-42", "job_1.attempt:2", "A-Za-z0-9._:-", "x" * 255])
    def test_accepts_1_to_255_allowed_chars(self, key: str) -> None:
        assert is_valid_idempotency_key(key)

    @pytest.mark.parametrize(
        "key", [None, "", "x" * 256, "has space", "slash/", "tab\t", "trailing\n", "ünicode", "a,b"]
    )
    def test_rejects_missing_empty_too_long_or_disallowed_chars(self, key: str | None) -> None:
        assert not is_valid_idempotency_key(key)


class TestCanonicalJson:
    @pytest.mark.parametrize("vector", _VECTORS, ids=[v["name"] for v in _VECTORS])
    def test_matches_shared_vectors(self, vector: dict[str, str]) -> None:
        value = json.loads(vector["json"])
        assert canonical_json(value) == vector["canonical"]
        assert body_hash(value) == vector["sha256"]

    def test_same_body_in_any_key_order_hashes_the_same(self) -> None:
        assert body_hash({"a": 1, "b": {"c": [1, 2], "d": None}}) == body_hash(
            {"b": {"d": None, "c": [1, 2]}, "a": 1}
        )

    def test_different_bodies_hash_differently(self) -> None:
        assert body_hash({"a": 1}) != body_hash({"a": 2})
        # An explicit null is part of the body, not the same as leaving the field out.
        assert body_hash({"a": 1}) != body_hash({"a": 1, "b": None})

    def test_tuples_serialize_like_lists(self) -> None:
        assert canonical_json((1, "a")) == canonical_json([1, "a"])

    @pytest.mark.parametrize(
        "value",
        [float("nan"), float("inf"), {1: "non-string key"}, {"a": object()}, b"bytes", 10**400],
    )
    def test_rejects_values_json_cannot_represent(self, value: Any) -> None:
        with pytest.raises(ValueError):
            canonical_json(value)

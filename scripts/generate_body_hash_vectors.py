"""Regenerate tests/fixtures/body_hash_vectors.json from this implementation.

The file is shared byte-for-byte with ts-async-contract (test/fixtures/), whose tests must pass
against it unchanged: copy it across after regenerating.

Run: python scripts/generate_body_hash_vectors.py
"""

import json
import pathlib

from py_async_contract import body_hash, canonical_json

# (name, raw JSON text): the text is parsed first, so formatting on the wire must not matter.
INPUTS = [
    (
        "llm-gateway submit body",
        r'{"project": "web_data_engine", "prompt_name": "check_blocked", '
        r'"prompt_params": {"screenshot_url": "https://cdn.example.com/s.png"}, '
        r'"webhook_url": "https://scraper.example.com/v1/webhook", "webhook_aud": "web-data-engine"}',
    ),
    ("key order and whitespace don't matter", '{ "b" : 1 ,\n "a" : [ 1 , 2 ] }'),
    ("nested objects sorted at every level", r'{"z": {"y": 1, "x": {"w": true, "v": false}}, "a": null}'),
    ("empty containers", r'{"o": {}, "l": [], "s": ""}'),
    ("array order is preserved", r"[3, 1, 2]"),
    ("integral floats print as integers", r"[1.0, -0.0, 100.0, 1e2]"),
    ("ECMAScript exponent thresholds", r"[1e20, 1e21, 1e-6, 1e-7, 123e-20, 2.5e-7]"),
    (
        "shortest round-trip digits",
        r"[0.30000000000000004, 123456.789, 4.35, 5e-324, 1.7976931348623157e308]",
    ),
    (
        "integers beyond 2^53 lose precision like JavaScript",
        r"[9007199254740991, 9007199254740993, 123456789012345678901234]",
    ),
    ("non-ASCII is emitted raw, not escaped", '{"name": "Ünïcödé ✓ 日本 😀"}'),
    (
        "control characters and quotes are escaped",
        r'"tab\t nl\n cr\r bs\b ff\f nul\u0000 us\u001f del\u007f quote\" backslash\\ slash\/"',
    ),
    ("lone surrogate is escaped", r'"\ud800 alone"'),
    ("keys sort by UTF-16 code units, not code points", r'{"￿": 1, "😀": 2, "a": 3, "é": 4}'),
    ("top-level scalars", r'[null, true, false, "x", 0]'),
]
vectors = [
    {
        "name": n,
        "json": raw,
        "canonical": canonical_json(json.loads(raw)),
        "sha256": body_hash(json.loads(raw)),
    }
    for n, raw in INPUTS
]
OUTPUT = pathlib.Path(__file__).parent.parent / "tests" / "fixtures" / "body_hash_vectors.json"
OUTPUT.write_text(json.dumps(vectors, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

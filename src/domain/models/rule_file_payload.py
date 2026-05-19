"""Rule file persistence envelope helpers.

Raw rule text remains supported for legacy records. New records can store an
envelope that keeps the rule text and graph edge-list payload together inside
the existing file blob, avoiding a database schema break during Phase 2.5.
"""

from __future__ import annotations

import json
from typing import Optional

PAYLOAD_TYPE = "inferra.rule_file"
PAYLOAD_VERSION = 2


def encode_rule_file_payload(
    rule_text: str,
    graph_json: str,
    source_hash: str,
) -> bytearray:
    graph_payload = json.loads(graph_json)
    payload = {
        "type": PAYLOAD_TYPE,
        "version": PAYLOAD_VERSION,
        "rule_text": rule_text,
        "graph": graph_payload,
        "source_hash": source_hash,
    }
    return bytearray(json.dumps(payload, sort_keys=True).encode("utf-8"))


def decode_rule_file_text(files: bytes) -> str:
    text = files.decode("utf-8")
    payload = _loads_payload(text)
    if payload is None:
        return text
    return str(payload.get("rule_text", ""))


def decode_rule_file_graph_json(files: bytes) -> Optional[str]:
    text = files.decode("utf-8")
    payload = _loads_payload(text)
    if payload is None:
        return None
    graph_payload = payload.get("graph")
    if graph_payload is None:
        return None
    return json.dumps(graph_payload, sort_keys=True)


def _loads_payload(text: str) -> Optional[dict]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("type") != PAYLOAD_TYPE:
        return None
    if "rule_text" not in payload:
        return None
    return payload

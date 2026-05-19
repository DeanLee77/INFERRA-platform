import json

import pytest

from src.domain.models.rule import RuleFileEntity
from src.domain.models.rule_file_payload import (
    PAYLOAD_TYPE,
    decode_rule_file_graph_json,
    decode_rule_file_text,
    encode_rule_file_payload,
)


def test_rule_file_payload_roundtrips_text_and_graph():
    payload = encode_rule_file_payload(
        rule_text="goal\n",
        graph_json=json.dumps({"schema_version": 1, "nodes": [], "edges": []}),
        source_hash="abc",
    )

    entity = RuleFileEntity(files=bytes(payload))

    assert entity.decode_files() == "goal\n"
    assert json.loads(entity.decode_graph_json()) == {
        "schema_version": 1,
        "nodes": [],
        "edges": [],
    }


def test_raw_legacy_rule_text_has_no_graph_payload():
    assert decode_rule_file_text(b"plain rule") == "plain rule"
    assert decode_rule_file_graph_json(b"plain rule") is None


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"type": "other", "rule_text": "x"},
        {"type": PAYLOAD_TYPE},
        {"type": PAYLOAD_TYPE, "rule_text": "x"},
    ],
)
def test_invalid_or_incomplete_envelopes_fall_back_safely(payload):
    raw = json.dumps(payload).encode("utf-8")

    if isinstance(payload, dict) and payload.get("type") == PAYLOAD_TYPE and "rule_text" in payload:
        assert decode_rule_file_text(raw) == "x"
    else:
        assert decode_rule_file_text(raw) == json.dumps(payload)
    assert decode_rule_file_graph_json(raw) is None


def test_decode_graph_requires_stored_content():
    with pytest.raises(ValueError, match="No file content stored"):
        RuleFileEntity().decode_graph_json()

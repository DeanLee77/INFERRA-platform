"""Focused edge coverage for AEGIS session-snapshot materialization."""

import pytest

from src.domain.aegis.session_snapshot import (
    SessionSnapshotConsistencyError,
    build_session_snapshot,
)


def test_snapshot_rejects_non_contiguous_event_sequences() -> None:
    with pytest.raises(SessionSnapshotConsistencyError, match="expected 1, got 2"):
        build_session_snapshot(
            run={"runId": "run-gap", "workflowId": "workflow"},
            action_proposal={},
            events=[{"sequence": 2}],
        )


def test_empty_snapshot_uses_zero_sequence_range_and_empty_actor() -> None:
    snapshot = build_session_snapshot(
        run={"runId": "run-empty", "workflowId": "workflow"},
        action_proposal={},
        events=[],
    )

    assert snapshot["run"]["eventSequenceRange"] == [0, 0]
    assert snapshot["actor"] == {}
    assert snapshot["events"] == []


def test_snapshot_materializes_embedded_evidence_and_payload_correction() -> None:
    snapshot = build_session_snapshot(
        run={"runId": "run-correction", "workflowId": "workflow"},
        action_proposal={
            "receiptHash": "sha256:proposal-receipt",
            "sla": {"state": "pending"},
        },
        events=[
            {
                "eventId": "event-correction-1",
                "sequence": 1,
                "type": "correction.applied",
                "payload": {
                    "extractedFacts": [
                        None,
                        {},
                        {"factName": "claim accepted", "value": True},
                    ],
                    "evidence": [
                        {
                            "id": "evidence-embedded",
                            "contentHash": "sha256:evidence",
                        }
                    ],
                    "sla": {"state": "met"},
                    "correctsEventId": "event-original",
                    "reason": "Corrected extracted claim state",
                    "patch": {"claim accepted": True},
                },
            }
        ],
    )

    assert snapshot["facts"]["claim accepted"] is True
    assert snapshot["factProvenance"]["claim accepted"]["eventId"] == (
        "event-correction-1"
    )
    assert snapshot["evidence"] == {
        "refs": ["evidence-embedded"],
        "hashes": {"evidence-embedded": "sha256:evidence"},
    }
    assert snapshot["sla"] == {"state": "met"}
    assert snapshot["receipt"]["receiptHash"] == "sha256:proposal-receipt"
    assert snapshot["corrections"] == [
        {
            "eventId": "event-correction-1",
            "sequence": 1,
            "correctsEventId": "event-original",
            "reason": "Corrected extracted claim state",
            "patch": {"claim accepted": True},
        }
    ]

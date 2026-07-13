"""AEGIS SessionSnapshot materialization from append-only ledger events."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from src.domain.aegis.rule_store import stable_hash


class SessionSnapshotConsistencyError(ValueError):
    """Raised when ledger events cannot produce a coherent snapshot."""


def build_session_snapshot(
    *,
    run: dict[str, Any],
    action_proposal: dict[str, Any],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Materialize a liability snapshot from stored run/proposal rows and ledger events."""

    ordered_events = _ordered_events(events)
    sequence_range = _sequence_range(ordered_events)
    proposal_payload = deepcopy(action_proposal.get("proposal") or action_proposal.get("proposalPayload") or {})
    actor = _first_dict(action_proposal.get("actor"), run.get("actor"))
    facts, fact_provenance = _fact_state(run, action_proposal, ordered_events)
    policy = _policy_state(run, action_proposal, ordered_events)
    evidence = _evidence_state(action_proposal, ordered_events)
    options = _option_state(action_proposal, ordered_events)
    approval = _approval_state(action_proposal, ordered_events)
    fallback = _fallback_state(action_proposal, ordered_events)
    sla = _latest_payload_value(action_proposal.get("sla"), ordered_events, "sla") or {}
    gate_decision = _gate_decision(action_proposal, ordered_events)
    receipt = _receipt_state(action_proposal, ordered_events)
    corrections = _corrections(ordered_events)
    compact_events = [_compact_event(event) for event in ordered_events]

    snapshot = {
        "schemaVersion": "aegis-session-snapshot-v1",
        "run": {
            "runId": run["runId"],
            "workflowId": run["workflowId"],
            "workflowVersionId": run.get("workflowVersionId"),
            "status": run.get("status"),
            "eventSequenceRange": sequence_range,
            "eventCount": len(ordered_events),
        },
        "proposal": proposal_payload,
        "actor": actor,
        "facts": facts,
        "factProvenance": fact_provenance,
        "evidence": evidence,
        "policy": policy,
        "options": options,
        "approval": approval,
        "fallback": fallback,
        "sla": sla,
        "gateDecision": gate_decision,
        "receipt": receipt,
        "corrections": corrections,
        "events": compact_events,
    }
    snapshot["sectionHashes"] = {
        "proposalHash": stable_hash(snapshot["proposal"]),
        "evidenceHash": stable_hash(snapshot["evidence"]),
        "policyHash": stable_hash(snapshot["policy"]),
        "optionSetHash": stable_hash(snapshot["options"]),
        "approvalHash": stable_hash(snapshot["approval"]),
        "fallbackHash": stable_hash(snapshot["fallback"]),
        "receiptHash": receipt.get("receiptHash") or stable_hash(snapshot["receipt"]),
    }
    snapshot["snapshotHash"] = stable_hash(
        {
            "schemaVersion": snapshot["schemaVersion"],
            "run": snapshot["run"],
            "sectionHashes": snapshot["sectionHashes"],
            "corrections": snapshot["corrections"],
        }
    )
    return snapshot


def _ordered_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted((deepcopy(event) for event in events), key=lambda item: int(item["sequence"]))
    expected = 1
    for event in ordered:
        sequence = int(event["sequence"])
        if sequence != expected:
            raise SessionSnapshotConsistencyError(
                f"AEGIS event sequence is not contiguous: expected {expected}, got {sequence}"
            )
        expected += 1
    return ordered


def _sequence_range(events: list[dict[str, Any]]) -> list[int]:
    if not events:
        return [0, 0]
    return [int(events[0]["sequence"]), int(events[-1]["sequence"])]


def _first_dict(*values: Any) -> dict[str, Any]:
    for value in values:
        if isinstance(value, dict):
            return deepcopy(value)
    return {}


def _merge_dicts(*values: Any) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for value in values:
        if isinstance(value, dict):
            merged.update(deepcopy(value))
    return merged


def _fact_state(
    run: dict[str, Any],
    action_proposal: dict[str, Any],
    events: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    values = _merge_dicts(run.get("facts"), action_proposal.get("facts"))
    provenance: dict[str, dict[str, Any]] = {}

    proposal_refs = _unique_strings(action_proposal.get("evidenceRefs"))
    proposal_hashes = _merge_dicts(action_proposal.get("evidenceHashes"))
    for fact_name, fact_value in values.items():
        record = _fact_record(
            fact_name=str(fact_name),
            value=fact_value,
            authority_class="asserted",
            extraction_method="proposal_assertion",
            confidence=1.0,
            source_refs=proposal_refs,
            source_hashes=[proposal_hashes[ref] for ref in proposal_refs if ref in proposal_hashes],
            provenance_source="proposal.facts",
        )
        provenance[str(fact_name)] = record

    for event in events:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        extracted_facts = payload.get("extractedFacts")
        if not isinstance(extracted_facts, list):
            continue
        for fact in extracted_facts:
            if not isinstance(fact, dict) or not fact.get("factName"):
                continue
            fact_name = str(fact["factName"])
            values[fact_name] = deepcopy(fact.get("value"))
            record = deepcopy(fact)
            record.setdefault("eventId", event.get("eventId"))
            record.setdefault("sequence", event.get("sequence"))
            provenance[fact_name] = record

    return values, provenance


def _fact_record(
    *,
    fact_name: str,
    value: Any,
    authority_class: str,
    extraction_method: str,
    confidence: float,
    source_refs: list[str],
    source_hashes: list[str],
    provenance_source: str,
) -> dict[str, Any]:
    can_satisfy = authority_class in {"asserted", "inferred"} and bool(source_refs) and bool(source_hashes)
    return {
        "factName": fact_name,
        "value": deepcopy(value),
        "authorityClass": authority_class,
        "extractionMethod": extraction_method,
        "confidence": confidence,
        "sourceRefs": deepcopy(source_refs),
        "sourceHashes": deepcopy(source_hashes),
        "provenance": {"source": provenance_source},
        "canSatisfyAuthoritativeRules": can_satisfy,
        "advisoryOnly": not can_satisfy,
    }


def _latest_payload_value(default: Any, events: list[dict[str, Any]], key: str) -> Any:
    latest = deepcopy(default) if default is not None else None
    for event in events:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if key in payload:
            latest = deepcopy(payload[key])
    return latest


def _policy_state(run: dict[str, Any], action_proposal: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    policy = _merge_dicts(run.get("policyHashes"), action_proposal.get("policyHashes"))
    for event in events:
        policy.update(_merge_dicts(event.get("policyHashes")))
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        policy.update(_merge_dicts(payload.get("policyHashes"), payload.get("policyIntegrity")))
    return policy


def _evidence_state(action_proposal: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    refs = _unique_strings(action_proposal.get("evidenceRefs"))
    hashes = _merge_dicts(action_proposal.get("evidenceHashes"))
    for event in events:
        refs.extend(ref for ref in _unique_strings(event.get("evidenceRefs")) if ref not in refs)
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        refs.extend(ref for ref in _unique_strings(payload.get("evidenceRefs")) if ref not in refs)
        hashes.update(_merge_dicts(payload.get("evidenceHashes")))
        for evidence in payload.get("evidence", []) if isinstance(payload.get("evidence"), list) else []:
            if isinstance(evidence, dict) and evidence.get("id") and evidence.get("contentHash"):
                hashes[str(evidence["id"])] = str(evidence["contentHash"])
                if str(evidence["id"]) not in refs:
                    refs.append(str(evidence["id"]))
    return {"refs": refs, "hashes": hashes}


def _option_state(action_proposal: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    option_set = _merge_dicts(action_proposal.get("optionSet"))
    considered = deepcopy(option_set.get("considered") or action_proposal.get("optionsConsidered") or [])
    selected = option_set.get("selectedOptionId") or action_proposal.get("selectedOptionId")
    rejected = deepcopy(option_set.get("rejectedOptionIds") or action_proposal.get("rejectedOptionIds") or [])
    for event in events:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        event_option_set = _merge_dicts(event.get("optionSet"), payload.get("optionSet"))
        if "considered" in event_option_set:
            considered = deepcopy(event_option_set["considered"])
        if "selectedOptionId" in event_option_set:
            selected = event_option_set["selectedOptionId"]
        if "rejectedOptionIds" in event_option_set:
            rejected = deepcopy(event_option_set["rejectedOptionIds"])
        if "selectedOptionId" in payload:
            selected = payload["selectedOptionId"]
        if "rejectedOptionIds" in payload:
            rejected = deepcopy(payload["rejectedOptionIds"])
    return {
        "considered": considered,
        "selectedOptionId": selected,
        "rejectedOptionIds": rejected,
    }


def _approval_state(action_proposal: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    approval = _merge_dicts(action_proposal.get("approval"))
    approver_chain = deepcopy(action_proposal.get("approverChain") or approval.get("approverChain") or [])
    for event in events:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        approval.update(_merge_dicts(event.get("approvalState"), payload.get("approval")))
        if event.get("type", "").startswith("approval."):
            approval["status"] = str(event["type"]).split(".", 1)[1]
            approval["eventId"] = event["eventId"]
        if "approverChain" in payload:
            approver_chain = deepcopy(payload["approverChain"])
    approval["approverChain"] = approver_chain
    return approval


def _fallback_state(action_proposal: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    fallback = _merge_dicts(action_proposal.get("fallback"))
    for event in events:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        fallback.update(_merge_dicts(event.get("fallbackState"), payload.get("fallback")))
        if event.get("type", "").startswith("fallback."):
            fallback["triggerEventId"] = event["eventId"]
            fallback["state"] = str(event["type"]).split(".", 1)[1]
    return fallback


def _gate_decision(action_proposal: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    decision = _merge_dicts(action_proposal.get("gateDecision"))
    for event in events:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        decision.update(_merge_dicts(payload.get("gateDecision"), payload.get("ruleGate"), payload.get("gate")))
        if event.get("type") == "rule.evaluation.completed":
            decision.setdefault("eventId", event["eventId"])
    return decision


def _receipt_state(action_proposal: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    receipt = _merge_dicts(action_proposal.get("receipt"))
    if action_proposal.get("receiptHash"):
        receipt["receiptHash"] = action_proposal["receiptHash"]
    for event in events:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        receipt.update(_merge_dicts(event.get("receipt"), payload.get("receipt")))
        if payload.get("receiptHash"):
            receipt["receiptHash"] = payload["receiptHash"]
        if event.get("type", "").startswith("receipt."):
            receipt.setdefault("eventId", event["eventId"])
            receipt["signatureState"] = str(event["type"]).split(".", 1)[1]
    return receipt


def _corrections(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    corrections = []
    for event in events:
        correction_target = event.get("correctionOfEventId")
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if not correction_target and payload.get("correctsEventId"):
            correction_target = payload["correctsEventId"]
        if correction_target:
            corrections.append(
                {
                    "eventId": event["eventId"],
                    "sequence": event["sequence"],
                    "correctsEventId": correction_target,
                    "reason": payload.get("reason"),
                    "patch": deepcopy(payload.get("patch") or {}),
                }
            )
    return corrections


def _compact_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "eventId": event["eventId"],
        "sequence": event["sequence"],
        "type": event["type"],
        "idempotencyKey": event.get("idempotencyKey"),
        "eventHash": event.get("eventHash"),
        "previousHash": event.get("previousHash"),
        "correctionOfEventId": event.get("correctionOfEventId"),
        "evidenceRefs": deepcopy(event.get("evidenceRefs") or []),
    }


def _unique_strings(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    unique: list[str] = []
    for value in values:
        text = str(value)
        if text not in unique:
            unique.append(text)
    return unique

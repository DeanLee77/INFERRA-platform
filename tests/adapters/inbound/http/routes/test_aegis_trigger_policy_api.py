from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.adapters.inbound.http.dependencies import get_aegis_db_session, get_session_store
from src.adapters.outbound.persistence import database
from src.adapters.outbound.persistence.models import (
    AegisActionProposalORM,
    AegisEventLedgerEntryORM,
    AegisFileORM,
    AegisHistoryORM,
    AegisRuleORM,
    AegisSessionSnapshotORM,
    AegisTriggerPolicyORM,
    AegisTriggerReceiptORM,
    AegisWorkflowDefinitionORM,
    AegisWorkflowRunORM,
    AegisWorkflowVersionORM,
)
from src.adapters.outbound.session.in_memory_session_store import InMemorySessionStore
from src.domain.state.fact_source import FactSource
from src.domain.state.feature_flags import FeatureFlags
from src.main import app


SOURCE_RULE_TEXT = """INPUT source flag AS BOOLEAN

source complete
    AND source flag IS true
"""

TARGET_RULE_TEXT = """INPUT age AS NUMBER

eligible
    AND age >= 18
"""

IMPORT_ROOT_TEXT = """IMPORT: trigger_common

eligible imported
    AND imported age >= minimum imported age
"""

IMPORT_COMMON_TEXT = """INPUT imported age AS NUMBER
FIXED minimum imported age IS 18
"""


def _tables():
    return [
        AegisRuleORM.__table__,
        AegisFileORM.__table__,
        AegisHistoryORM.__table__,
        AegisWorkflowDefinitionORM.__table__,
        AegisWorkflowVersionORM.__table__,
        AegisWorkflowRunORM.__table__,
        AegisActionProposalORM.__table__,
        AegisEventLedgerEntryORM.__table__,
        AegisSessionSnapshotORM.__table__,
        AegisTriggerPolicyORM.__table__,
        AegisTriggerReceiptORM.__table__,
    ]


def _seed_rule(db, rule_id: int, name: str, text: str) -> None:
    rule = AegisRuleORM(
        rule_name=name,
        rule_category="AEGIS Trigger Test",
        rule_description="Synthetic trigger policy fixture",
    )
    rule.rule_id = rule_id
    file_orm = AegisFileORM(rule_id=rule_id, files=bytearray(text.encode("utf-8")))
    file_orm.file_id = rule_id
    db.add(rule)
    db.add(file_orm)
    db.commit()


def _seed_default_rules(session_local) -> None:
    db = session_local()
    try:
        _seed_rule(db, 1, "source_rule", SOURCE_RULE_TEXT)
        _seed_rule(db, 2, "target_rule", TARGET_RULE_TEXT)
        _seed_rule(db, 3, "cycle_rule_a", TARGET_RULE_TEXT)
        _seed_rule(db, 4, "cycle_rule_b", TARGET_RULE_TEXT)
        _seed_rule(db, 5, "trigger_common", IMPORT_COMMON_TEXT)
        _seed_rule(db, 6, "trigger_import_root", IMPORT_ROOT_TEXT)
    finally:
        db.close()


def _client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    database.Base.metadata.create_all(bind=engine, tables=_tables())
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    _seed_default_rules(SessionLocal)
    store = InMemorySessionStore()

    def _override_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_aegis_db_session] = _override_db
    app.dependency_overrides[get_session_store] = lambda: store
    return TestClient(app), store


def test_outcome_trigger_executes_downstream_rule_set_with_filtered_fact_sources():
    client, store = _client()
    try:
        policy = client.post(
            "/api/v1/aegis/trigger-policies",
            json={
                "policyId": "policy-source-to-target",
                "mode": "automatic",
                "source": {"type": "rule_set", "ruleName": "source_rule"},
                "target": {
                    "type": "rule_set",
                    "ruleName": "target_rule",
                    "targetNodeName": "eligible",
                },
                "when": {"outcome": True},
                "constraints": {
                    "factSourceFilter": ["ASSERTED"],
                    "confidenceThreshold": 0.75,
                    "maxDepth": 3,
                },
            },
        )
        assert policy.status_code == 200

        response = client.post(
            "/api/v1/aegis/triggers/outcome",
            json={
                "policyId": "policy-source-to-target",
                "idempotencyKey": "outcome-trigger-1",
                "correlationId": "corr-outcome-1",
                "actor": {"kind": "system", "id": "trigger-runtime", "role": "workflow runtime"},
                "sourceResult": {
                    "ruleName": "source_rule",
                    "outcome": True,
                    "confidence": 0.91,
                    "facts": {
                        "age": {"value": 21, "source": "ASSERTED"},
                        "advisory note": {"value": "ignore", "source": "SEMANTIC"},
                    },
                },
            },
        )

        assert response.status_code == 200
        receipt = response.json()["triggerReceipt"]
        assert receipt["decision"] == "executed"
        assert receipt["execution"]["type"] == "rule_set"
        assert receipt["execution"]["ruleName"] == "target_rule"
        assert receipt["factsPassed"] == {
            "age": {"value": 21, "source": "ASSERTED", "valueType": "INTEGER"}
        }
        source_event = receipt["payload"]["sourceEvent"]
        assert "facts" not in source_event
        assert source_event["factSummary"] == {
            "count": 2,
            "sourceCounts": {"ASSERTED": 1, "SEMANTIC": 1},
        }

        session = store.get(receipt["execution"]["sessionId"])
        assert session is not None
        fact_store = session.inference_engine.get_assessment_state().get_fact_store()
        assert fact_store.get_fact_sources("age") == {FactSource.ASSERTED}
        assert fact_store.peek_in_layer("advisory note", FactSource.SEMANTIC) is None
    finally:
        app.dependency_overrides.clear()
        client.close()


def test_outcome_trigger_preserves_false_outcome_semantics():
    client, store = _client()
    try:
        policy = client.post(
            "/api/v1/aegis/trigger-policies",
            json={
                "policyId": "policy-source-false-to-target",
                "mode": "automatic",
                "source": {"type": "rule_set", "ruleName": "source_rule"},
                "target": {
                    "type": "rule_set",
                    "ruleName": "target_rule",
                    "targetNodeName": "eligible",
                },
                "when": {"outcome": False},
            },
        )
        assert policy.status_code == 200

        response = client.post(
            "/api/v1/aegis/triggers/outcome",
            json={
                "policyId": "policy-source-false-to-target",
                "idempotencyKey": "outcome-trigger-false-1",
                "actor": {"kind": "system", "id": "trigger-runtime", "role": "workflow runtime"},
                "sourceResult": {
                    "ruleName": "source_rule",
                    "outcome": False,
                    "facts": {"age": {"value": 21, "source": "ASSERTED"}},
                },
            },
        )

        assert response.status_code == 200
        receipt = response.json()["triggerReceipt"]
        assert receipt["decision"] == "executed"
        assert receipt["status"] == "started"
        assert receipt["payload"]["sourceEvent"]["outcome"] is False
        assert store.get(receipt["execution"]["sessionId"]) is not None
    finally:
        app.dependency_overrides.clear()
        client.close()


def test_direct_trigger_can_start_governed_action_proposal_and_replay_idempotently():
    client, _ = _client()
    try:
        policy = client.post(
            "/api/v1/aegis/trigger-policies",
            json={
                "policyId": "policy-direct-action",
                "mode": "automatic",
                "source": {"type": "direct", "eventType": "operator.release"},
                "target": {
                    "type": "action",
                    "workflowId": "robot-action-firewall",
                    "action": {"kind": "robot.reroute", "target": "AMR-17"},
                },
                "constraints": {"factSourceFilter": ["ASSERTED", "INFERRED"]},
            },
        )
        assert policy.status_code == 200

        payload = {
            "policyId": "policy-direct-action",
            "idempotencyKey": "direct-action-1",
            "targetRunId": "trigger-action-run-1",
            "correlationId": "corr-direct-1",
            "actor": {"kind": "human", "id": "operator-1", "role": "operator"},
            "facts": {"batteryReservePercent": {"value": 61, "source": "ASSERTED"}},
            "evidenceRefs": ["ev-battery-reserve"],
        }
        response = client.post("/api/v1/aegis/triggers/direct", json=payload)
        replay = client.post("/api/v1/aegis/triggers/direct", json=payload)

        assert response.status_code == 200
        assert replay.status_code == 200
        receipt = response.json()["triggerReceipt"]
        replay_receipt = replay.json()["triggerReceipt"]
        assert receipt["decision"] == "executed"
        assert receipt["execution"]["type"] == "action"
        assert receipt["execution"]["runId"] == "trigger-action-run-1"
        assert replay.json()["idempotentReplay"] is True
        assert replay_receipt["triggerRunId"] == receipt["triggerRunId"]
    finally:
        app.dependency_overrides.clear()
        client.close()


def test_direct_trigger_rejects_reused_idempotency_key_with_different_content():
    client, _ = _client()
    try:
        policy = client.post(
            "/api/v1/aegis/trigger-policies",
            json={
                "policyId": "policy-direct-conflict",
                "mode": "automatic",
                "source": {"type": "direct", "eventType": "operator.release"},
                "target": {
                    "type": "action",
                    "workflowId": "robot-action-firewall",
                    "action": {"kind": "robot.reroute", "target": "AMR-17"},
                },
            },
        )
        assert policy.status_code == 200

        first = {
            "policyId": "policy-direct-conflict",
            "idempotencyKey": "direct-conflict-1",
            "targetRunId": "trigger-action-conflict-1",
            "actor": {"kind": "human", "id": "operator-1", "role": "operator"},
            "facts": {"batteryReservePercent": {"value": 61, "source": "ASSERTED"}},
        }
        replay_with_changed_content = {
            **first,
            "facts": {"batteryReservePercent": {"value": 12, "source": "ASSERTED"}},
        }

        assert client.post("/api/v1/aegis/triggers/direct", json=first).status_code == 200
        conflict = client.post("/api/v1/aegis/triggers/direct", json=replay_with_changed_content)

        assert conflict.status_code == 409
        assert "reused with different content" in conflict.json()["detail"]
    finally:
        app.dependency_overrides.clear()
        client.close()


def test_direct_trigger_requires_aegis_write_scope_when_auth_enabled():
    client, _ = _client()
    flags = FeatureFlags(auth_enabled=True)
    try:
        with (
            patch("src.infrastructure.auth_middleware.get_feature_flags", return_value=flags),
            patch("src.adapters.inbound.http.dependencies.get_feature_flags", return_value=flags),
            patch.dict(
                "os.environ",
                {"INFERRA_API_KEY": "test-key", "INFERRA_API_KEY_SCOPES": "read"},
                clear=False,
            ),
        ):
            response = client.post(
                "/api/v1/aegis/triggers/direct",
                headers={"x-api-key": "test-key"},
                json={"policyId": "policy-direct-auth", "idempotencyKey": "direct-auth-1"},
            )

        assert response.status_code == 403
        assert response.json()["detail"] == "Missing required scope: aegis:write"
    finally:
        app.dependency_overrides.clear()
        client.close()


def test_direct_trigger_rejects_unauthorized_actor_role():
    client, _ = _client()
    try:
        policy = client.post(
            "/api/v1/aegis/trigger-policies",
            json={
                "policyId": "policy-direct-denied",
                "mode": "recommend_only",
                "source": {"type": "direct", "eventType": "operator.release"},
                "target": {
                    "type": "rule_set",
                    "ruleName": "target_rule",
                    "targetNodeName": "eligible",
                },
            },
        )
        assert policy.status_code == 200

        response = client.post(
            "/api/v1/aegis/triggers/direct",
            json={
                "policyId": "policy-direct-denied",
                "idempotencyKey": "direct-denied-1",
                "actor": {"kind": "human", "id": "auditor-1", "role": "auditor"},
            },
        )

        assert response.status_code == 403
        assert "not authorized" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()
        client.close()


def test_rule_set_trigger_policy_rejects_cycles():
    client, _ = _client()
    try:
        first = client.post(
            "/api/v1/aegis/trigger-policies",
            json={
                "policyId": "cycle-a-to-b",
                "mode": "recommend_only",
                "source": {"type": "rule_set", "ruleName": "cycle_rule_a"},
                "target": {
                    "type": "rule_set",
                    "ruleName": "cycle_rule_b",
                    "targetNodeName": "eligible",
                },
            },
        )
        assert first.status_code == 200

        second = client.post(
            "/api/v1/aegis/trigger-policies",
            json={
                "policyId": "cycle-b-to-a",
                "mode": "recommend_only",
                "source": {"type": "rule_set", "ruleName": "cycle_rule_b"},
                "target": {
                    "type": "rule_set",
                    "ruleName": "cycle_rule_a",
                    "targetNodeName": "eligible",
                },
            },
        )

        assert second.status_code == 409
        assert "cycle" in second.json()["detail"]
    finally:
        app.dependency_overrides.clear()
        client.close()


def test_trigger_depth_guardrail_records_skipped_receipt_without_execution():
    client, _ = _client()
    try:
        policy = client.post(
            "/api/v1/aegis/trigger-policies",
            json={
                "policyId": "policy-depth",
                "mode": "automatic",
                "source": {"type": "rule_set", "ruleName": "source_rule"},
                "target": {
                    "type": "rule_set",
                    "ruleName": "target_rule",
                    "targetNodeName": "eligible",
                },
                "constraints": {"maxDepth": 1},
            },
        )
        assert policy.status_code == 200

        response = client.post(
            "/api/v1/aegis/triggers/outcome",
            json={
                "policyId": "policy-depth",
                "idempotencyKey": "depth-guard-1",
                "depth": 1,
                "actor": {"kind": "system", "id": "trigger-runtime", "role": "workflow runtime"},
                "sourceResult": {"ruleName": "source_rule", "outcome": True},
            },
        )

        assert response.status_code == 200
        receipt = response.json()["triggerReceipt"]
        assert receipt["decision"] == "blocked"
        assert receipt["status"] == "skipped"
        assert receipt["guardrail"]["reason"] == "max_depth_exceeded"
        assert receipt["execution"] == {"status": "not_started"}
    finally:
        app.dependency_overrides.clear()
        client.close()


def test_trigger_policy_target_validation_keeps_import_resolution_regression_green():
    client, store = _client()
    try:
        policy = client.post(
            "/api/v1/aegis/trigger-policies",
            json={
                "policyId": "policy-import-target",
                "mode": "automatic",
                "source": {"type": "direct", "eventType": "manual.import"},
                "target": {
                    "type": "rule_set",
                    "ruleName": "trigger_import_root",
                    "targetNodeName": "eligible imported",
                },
            },
        )
        assert policy.status_code == 200

        response = client.post(
            "/api/v1/aegis/triggers/direct",
            json={
                "policyId": "policy-import-target",
                "idempotencyKey": "import-target-1",
                "actor": {"kind": "human", "id": "operator-1", "role": "operator"},
                "facts": {"imported age": {"value": 21, "source": "ASSERTED"}},
            },
        )

        assert response.status_code == 200
        receipt = response.json()["triggerReceipt"]
        assert receipt["decision"] == "executed"
        assert store.get(receipt["execution"]["sessionId"]) is not None
    finally:
        app.dependency_overrides.clear()
        client.close()

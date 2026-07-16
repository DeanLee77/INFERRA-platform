from unittest.mock import MagicMock

import pytest

from src.domain.aegis import workflow_authoring
from src.domain.aegis.workflow_authoring import (
    AegisWorkflowAuthoringService,
    _has_value,
    _node_field,
    _value_at,
)


def _service(*, rule_service=None):
    repository = MagicMock()
    return AegisWorkflowAuthoringService(repository, rule_service=rule_service), repository


def _valid_validation():
    return {
        "valid": True,
        "severityCounts": {"error": 0, "warning": 0, "info": 0},
        "diagnostics": [],
        "ruleBindings": [],
        "validatedAt": "2026-01-01T00:00:00Z",
    }


def test_value_helpers_handle_scalar_paths_strings_and_policy_binding_fallbacks():
    assert _value_at({"outer": 1}, "outer.inner") is None
    assert _has_value({"value": "   "}, "value") is False
    assert _node_field({"policyBinding": {"ruleName": "fallback-rule"}}, "ruleName") == (
        "fallback-rule"
    )
    assert _node_field({"policyBinding": "invalid"}, "ruleName") is None


def test_workflow_reads_handle_lists_missing_definitions_and_unversioned_definitions():
    service, repository = _service()
    repository.list_definitions.return_value = [{"id": "one"}]

    assert service.list_workflows() == [{"id": "one"}]

    repository.get_definition.return_value = None
    with pytest.raises(LookupError, match="missing"):
        service.get_workflow("missing")

    repository.get_definition.return_value = {"id": "unversioned"}
    repository.get_latest_version.return_value = None
    assert service.get_workflow("unversioned") == {"id": "unversioned"}


def test_regeneration_rejects_missing_source_and_unknown_workflow():
    service, repository = _service()

    with pytest.raises(ValueError, match="required for regeneration"):
        service.regenerate_workflow({})

    repository.get_latest_version.return_value = None
    with pytest.raises(LookupError, match="unknown"):
        service.regenerate_workflow({"sourceWorkflowId": "unknown"})


def test_extension_validates_source_and_persists_generated_draft(monkeypatch):
    service, repository = _service()

    with pytest.raises(ValueError, match="required for extension"):
        service.extend_workflow({})

    repository.get_latest_version.return_value = None
    with pytest.raises(LookupError, match="unknown"):
        service.extend_workflow({"workflowId": "unknown"})

    repository.get_latest_version.return_value = {"definition": {"id": "source"}}
    draft_id = MagicMock(return_value="source-extend-test")
    generate = MagicMock(return_value={"id": "source-extend-test"})
    persist = MagicMock(return_value={"workflow": {"id": "source-extend-test"}})
    monkeypatch.setattr(service, "_draft_workflow_id", draft_id)
    monkeypatch.setattr(service, "_generated_template_definition", generate)
    monkeypatch.setattr(service, "_persist_generated_workflow", persist)

    result = service.extend_workflow(
        {"sourceWorkflowId": "source", "createdBy": "workflow-owner"}
    )

    assert result["workflow"]["id"] == "source-extend-test"
    draft_id.assert_called_once_with(
        {"sourceWorkflowId": "source", "createdBy": "workflow-owner"},
        "extend",
        source_workflow_id="source",
    )
    generate.assert_called_once_with(
        "source-extend-test",
        {"sourceWorkflowId": "source", "createdBy": "workflow-owner"},
        generation_kind="extend",
        base_definition={"id": "source"},
    )
    persist.assert_called_once_with(
        {"id": "source-extend-test"}, created_by="workflow-owner"
    )


def test_missing_update_and_version_records_raise_clear_errors():
    service, repository = _service()
    repository.get_latest_version.return_value = None

    with pytest.raises(LookupError, match="missing"):
        service.update_workflow("missing", {})

    repository.get_version.return_value = None
    with pytest.raises(LookupError, match="version-missing"):
        service.get_version("workflow", "version-missing")

    repository.get_version.return_value = {"versionId": "version-1"}
    assert service.get_version("workflow", "version-1") == {"versionId": "version-1"}


def test_validate_workflow_accepts_payload_and_rejects_unknown_persisted_workflow(monkeypatch):
    service, repository = _service()
    validation = _valid_validation()
    validate = MagicMock(return_value=validation)
    monkeypatch.setattr(service, "validate_definition", validate)

    assert service.validate_workflow("draft", {"title": "Draft"}) is validation
    assert validate.call_args.args[0]["id"] == "draft"

    repository.get_latest_version.return_value = None
    with pytest.raises(LookupError, match="missing"):
        service.validate_workflow("missing")


def test_compile_payload_uses_draft_identity_without_persisting(monkeypatch):
    service, repository = _service()
    repository.get_latest_version.return_value = {
        "versionId": "version-1",
        "versionHash": "sha256:persisted",
        "graphHash": "sha256:persisted-graph",
        "definition": {"id": "workflow"},
    }
    validation = _valid_validation()
    monkeypatch.setattr(service, "validate_definition", MagicMock(return_value=validation))

    result = service.compile_workflow("workflow", {"title": "Changed draft"})

    assert result["status"] == "compiled"
    assert result["versionId"].startswith("draft-")
    repository.store_compile_output.assert_not_called()

    repository.get_latest_version.return_value = None
    with pytest.raises(LookupError, match="missing"):
        service.compile_workflow("missing")


def test_activation_approval_rejects_missing_manual_and_invalid_decisions():
    service, repository = _service()
    repository.get_latest_version.return_value = None
    with pytest.raises(LookupError, match="missing"):
        service.record_activation_approval("missing", {})

    repository.get_latest_version.return_value = {"definition": {"metadata": {}}}
    with pytest.raises(ValueError, match="only for generated"):
        service.record_activation_approval("manual", {})

    repository.get_latest_version.return_value = {
        "definition": {
            "metadata": {
                "generation": {
                    "generatedDraft": True,
                    "humanActivationApproval": {"status": "pending"},
                }
            }
        }
    }
    with pytest.raises(ValueError, match="approved or rejected"):
        service.record_activation_approval("generated", {"decision": "maybe"})


def test_activation_rejects_unknown_workflow():
    service, repository = _service()
    repository.get_latest_version.return_value = None

    with pytest.raises(LookupError, match="missing"):
        service.activate_workflow("missing", {})


def test_validate_definition_reports_empty_duplicate_and_non_object_nodes():
    service, _ = _service()

    empty = service.validate_definition({"id": "empty", "nodes": [], "transitions": []})
    assert {item["code"] for item in empty["diagnostics"]} >= {
        "EMPTY_WORKFLOW",
        "MISSING_START_NODE",
    }

    malformed = service.validate_definition(
        {
            "id": "malformed",
            "nodes": [None, {"id": "duplicate", "type": "INVALID"}, {"id": "duplicate"}],
            "transitions": [],
        }
    )
    assert {item["code"] for item in malformed["diagnostics"]} >= {
        "DUPLICATE_NODE_ID",
        "INVALID_NODE",
        "UNSANCTIONED_NODE_TYPE",
    }


def test_generated_identifiers_and_default_evidence_are_deterministic():
    service, _ = _service()
    payload = {"domain": "Warehouse Safety", "facts": "invalid", "evidenceRefs": "invalid"}

    first = service._draft_workflow_id(payload, "generate")
    second = service._draft_workflow_id(payload, "generate")
    assert first == second
    assert first.startswith("warehouse-safety-generate-")

    definition = service._generated_template_definition(
        "default-evidence",
        {},
        generation_kind="generate",
    )
    assert definition["evidence"][0]["id"] == "default-evidence-request-evidence"


def test_invalid_validation_always_blocks_activation():
    service, _ = _service()

    requirement = service._activation_requirement(
        {"metadata": {"generation": {"generatedDraft": True}}},
        {"valid": False, "severityCounts": {"error": 1}},
    )

    assert requirement["blocksActivation"] is True
    assert requirement["approvalRequired"] is True
    assert requirement["validation"]["valid"] is False


def test_node_and_option_contracts_report_unsupported_and_incomplete_payloads():
    service, _ = _service()
    diagnostics = []

    service._validate_node_contract({"id": "unsupported", "type": "CUSTOM"}, diagnostics)
    service._validate_node_contract({"id": "request", "type": "REQUEST"}, diagnostics)
    service._validate_options({"id": "empty", "options": []}, diagnostics)
    service._validate_options({"id": "options", "options": ["invalid", {}]}, diagnostics)

    codes = [item["code"] for item in diagnostics]
    assert "UNSANCTIONED_NODE_TYPE" in codes
    assert "MISSING_REQUIRED_PROOF_FIELD" in codes
    assert "INVALID_OPTION" in codes
    assert "MISSING_OPTION_PROOF_FIELD" in codes


def test_transition_validation_reports_malformed_and_unknown_endpoints():
    service, _ = _service()
    diagnostics = []
    nodes = {"known": {"id": "known", "type": "REQUEST"}}

    service._validate_transitions(
        [
            "invalid",
            {"from": "missing", "to": "known"},
            {"from": "known", "to": "missing"},
        ],
        nodes,
        diagnostics,
    )

    assert [item["code"] for item in diagnostics] == [
        "INVALID_TRANSITION",
        "UNKNOWN_TRANSITION_SOURCE",
        "UNKNOWN_TRANSITION_TARGET",
    ]


def test_reachability_handles_missing_anchors_non_objects_and_cycles():
    service, _ = _service()

    no_start = []
    service._validate_reachability([], [], {}, no_start)
    assert no_start[0]["code"] == "MISSING_START_NODE"

    request = {"id": "request", "type": "REQUEST"}
    no_receipt = []
    service._validate_reachability([request], [], {"request": request}, no_receipt)
    assert no_receipt[0]["code"] == "MISSING_RECEIPT_NODE"

    receipt = {"id": "receipt", "type": "RECEIPT_SEAL"}
    cyclic = []
    service._validate_reachability(
        [request, receipt],
        ["invalid", {"from": "request", "to": "request"}, {"from": "request", "to": "receipt"}],
        {"request": request, "receipt": receipt},
        cyclic,
    )
    assert cyclic == []


def test_evidence_validation_skips_non_objects_and_reports_unresolved_refs():
    service, _ = _service()
    diagnostics = []
    nodes = ["invalid", {"id": "consumer", "requiredEvidenceRefs": ["missing-evidence"]}]

    service._validate_evidence_contract({"evidence": []}, nodes, diagnostics)

    assert diagnostics[0]["code"] == "UNRESOLVED_EVIDENCE_REF"
    assert diagnostics[0]["evidenceRef"] == "missing-evidence"


def test_rule_binding_skips_unconfigured_rules_and_reports_integrity_failures(monkeypatch):
    service, _ = _service()
    diagnostics = []
    assert service._validate_rule_bindings(
        [{"id": "rule", "type": "RULE_GATE", "ruleName": "policy"}], diagnostics
    ) == []

    rule_service = MagicMock()
    latest_file = MagicMock(file_id=7)
    rule_service.get_latest_rule_file.return_value = latest_file
    rule_service.decode_rule_file.return_value = "policy text"
    rule_service.get_target_node_names.return_value = ["allowed-target"]
    service, _ = _service(rule_service=rule_service)
    monkeypatch.setattr(
        workflow_authoring,
        "build_policy_integrity",
        MagicMock(
            return_value={
                "ruleVersionHash": "sha256:rule",
                "importTreeHash": "sha256:imports",
                "validationStatus": "invalid",
                "missingImports": ["missing-import"],
                "hasImportCycles": True,
                "latestFileId": 7,
            }
        ),
    )
    diagnostics = []

    bindings = service._validate_rule_bindings(
        [
            {
                "id": "rule",
                "type": "RULE_GATE",
                "policyBinding": {"ruleName": "policy", "targetNodeName": "wrong-target"},
            }
        ],
        diagnostics,
    )

    assert bindings[0]["ruleName"] == "policy"
    assert {item["code"] for item in diagnostics} == {
        "INVALID_RULE_BINDING",
        "UNRESOLVED_IMPORT",
        "CIRCULAR_IMPORT",
        "INVALID_RULE_TARGET",
    }


def test_duplicate_node_detection_ignores_invalid_entries_and_finds_repeats():
    assert AegisWorkflowAuthoringService._duplicate_node_ids(
        [None, {}, {"id": "same"}, {"id": "same"}]
    ) == {"same"}

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from src.adapters.inbound.http.routes import aegis_rules


def _usage(*references):
    direct = [reference for reference in references if reference.bindingType == "direct"]
    indirect = [reference for reference in references if reference.bindingType == "indirect"]
    return aegis_rules.AegisRuleWorkflowUsageResponse(
        ruleName="target-rule",
        directWorkflowDefinitions=direct,
        indirectWorkflowDefinitions=indirect,
        summary=aegis_rules.AegisRuleWorkflowUsageSummary(
            directWorkflowDefinitions=len(direct),
            indirectWorkflowDefinitions=len(indirect),
            workflowRuns=0,
        ),
    )


def _reference(binding_type="direct", target_names=None):
    return aegis_rules.AegisRuleWorkflowReference(
        workflowId=f"workflow-{binding_type}",
        title="Workflow",
        domain="claims",
        status="validated",
        bindingType=binding_type,
        boundRuleNames=["target-rule"],
        nodeIds=["node-1"],
        nodeLabels=["Gate"],
        targetNodeNames=target_names or [],
    )


def test_integrity_summary_and_target_helpers_cover_degraded_metadata(monkeypatch):
    errors = aegis_rules._integrity_errors(
        {"missingImports": ["missing-rule"], "hasImportCycles": True}
    )
    assert [error.code for error in errors] == ["UNRESOLVED_IMPORT", "CIRCULAR_IMPORT"]

    service = MagicMock()
    service.get_latest_rule_file.side_effect = LookupError("missing")
    unnamed = aegis_rules._summary(
        service,
        {
            "rule_id": 1,
            "name": "",
            "category": "c",
            "description": "d",
            "target_node_name": " target ",
        },
    )
    assert unnamed.targetNodeName == "target"
    service.get_latest_rule_file.assert_not_called()

    missing_file = aegis_rules._summary(
        service,
        SimpleNamespace(
            rule_id=2,
            name="named",
            category="c",
            description="d",
            target_node_name=None,
        ),
    )
    assert missing_file.errors[0].code == "MISSING_RULE_FILE"
    assert aegis_rules._rule_target_node_name({"targetNodeName": None, "target_node_name": "fallback"}) == "fallback"
    assert aegis_rules._rule_target_node_name(SimpleNamespace(target_node_name="object-target")) == "object-target"
    assert aegis_rules._target_payload_value("   ") is None


def test_selected_target_validation_rejects_unknown_graph_node():
    service = MagicMock()
    service.get_target_node_names_for_text.return_value = ["goal"]
    service.get_node_names_for_text.return_value = ["goal", "input"]

    with pytest.raises(HTTPException) as caught:
        aegis_rules._validate_selected_target(service, "rule", "text", "missing")

    assert caught.value.status_code == 400
    assert caught.value.detail["graphNodeNames"] == ["goal", "input"]


def test_node_binding_helpers_use_direct_fields_then_policy_binding():
    node = {
        "ruleName": "direct",
        "policyBinding": {"ruleName": "bound", "targetNodeName": "target"},
    }
    assert aegis_rules._node_policy_binding({"policyBinding": []}) == {}
    assert aegis_rules._node_field(node, "ruleName") == "direct"
    assert aegis_rules._node_field(node, "targetNodeName") == "target"
    assert aegis_rules._node_rule_name(node) == "direct"
    assert aegis_rules._node_target_name(node) == "target"


def test_workflow_versions_skip_incomplete_records(monkeypatch):
    repository = MagicMock()
    repository.list_definitions.return_value = [
        {},
        {"id": "no-version"},
        {"id": "bad-payload"},
        {"id": "valid", "title": "Valid"},
    ]
    repository.get_latest_version.side_effect = [
        None,
        {"definition": []},
        {"definition": {"nodes": []}, "versionId": "v1"},
    ]
    monkeypatch.setattr(aegis_rules, "AegisWorkflowRepository", lambda db: repository)

    versions = aegis_rules._workflow_versions(object())

    assert len(versions) == 1
    assert versions[0][0]["id"] == "valid"


def test_import_name_lookup_is_fail_closed_and_returns_tree_names(monkeypatch):
    service = MagicMock()
    assert aegis_rules._import_names_for_rule(service, "") == set()
    service.get_rule_text.side_effect = LookupError("missing")
    assert aegis_rules._import_names_for_rule(service, "missing") == set()

    service.get_rule_text.side_effect = None
    service.get_rule_text.return_value = "IMPORT: child"
    monkeypatch.setattr(
        aegis_rules,
        "build_import_tree",
        lambda *_args: SimpleNamespace(
            imports=[SimpleNamespace(name="child"), SimpleNamespace(name="grandchild")]
        ),
    )
    assert aegis_rules._import_names_for_rule(service, "root") == {"child", "grandchild"}


def test_workflow_usage_identifies_direct_and_indirect_gate_bindings(monkeypatch):
    service = MagicMock()
    payload = {
        "nodes": [
            "invalid",
            {"id": "ignored", "type": "OTHER"},
            {"id": "empty", "type": "RULE_GATE"},
            {
                "id": "direct",
                "label": "Direct",
                "type": "RULE_GATE",
                "ruleName": "target-rule",
                "targetNodeName": "goal",
            },
            {
                "id": "indirect",
                "label": "Indirect",
                "type": "RULE_GATE",
                "policyBinding": {"ruleName": "root-rule", "targetNodeName": "root-goal"},
            },
        ]
    }
    monkeypatch.setattr(
        aegis_rules,
        "_workflow_versions",
        lambda db: [
            (
                {"id": "workflow", "title": "Workflow", "domain": "claims", "status": "draft"},
                {"versionId": "v1", "versionHash": "hash"},
                payload,
            )
        ],
    )
    monkeypatch.setattr(
        aegis_rules,
        "_import_names_for_rule",
        lambda _service, name: {"target-rule"} if name == "root-rule" else set(),
    )

    usage = aegis_rules._build_workflow_usage(service, object(), "target-rule")

    assert usage.summary.directWorkflowDefinitions == 1
    assert usage.summary.indirectWorkflowDefinitions == 1
    assert usage.directWorkflowDefinitions[0].nodeIds == ["direct"]
    assert usage.indirectWorkflowDefinitions[0].boundRuleNames == ["root-rule"]


def test_impact_test_reports_import_target_validation_and_binding_failures(monkeypatch):
    service = MagicMock()
    service.validate_draft_rule.return_value = SimpleNamespace(
        valid=False,
        errors=[SimpleNamespace(code="INVALID", message="bad", line=3)],
        warnings=[],
    )
    service.get_target_node_names_for_text.return_value = ["goal"]
    service.get_node_names_for_text.return_value = ["goal"]
    monkeypatch.setattr(aegis_rules, "_build_workflow_usage", lambda *_args: _usage(_reference(target_names=["old-goal"])))
    monkeypatch.setattr(
        aegis_rules,
        "build_import_tree",
        lambda *_args: SimpleNamespace(
            import_tree_hash="imports",
            missing=["missing-import"],
            has_cycles=True,
        ),
    )

    result = aegis_rules._build_workflow_impact_test(
        service,
        object(),
        "target-rule",
        "rule text",
        target_node_name="missing-target",
    )

    assert result.passed is False
    codes = {diagnostic.code for diagnostic in result.diagnostics}
    assert {"INVALID", "UNRESOLVED_IMPORT", "CIRCULAR_IMPORT", "INVALID_SELECTED_TARGET"} <= codes
    assert result.tests[0].status == "failed"
    assert any(item.code == "INVALID_RULE_TARGET" for item in result.tests[0].diagnostics)


@pytest.mark.parametrize("failure", ["imports", "targets"])
def test_impact_test_reports_helper_failures(monkeypatch, failure):
    service = MagicMock()
    service.validate_draft_rule.return_value = SimpleNamespace(valid=True, errors=[], warnings=[])
    service.get_target_node_names_for_text.return_value = ["goal"]
    service.get_node_names_for_text.return_value = ["goal"]
    monkeypatch.setattr(aegis_rules, "_build_workflow_usage", lambda *_args: _usage())
    if failure == "imports":
        monkeypatch.setattr(
            aegis_rules,
            "build_import_tree",
            MagicMock(side_effect=RuntimeError("import failure")),
        )
    else:
        monkeypatch.setattr(
            aegis_rules,
            "build_import_tree",
            lambda *_args: SimpleNamespace(
                import_tree_hash="imports", missing=[], has_cycles=False
            ),
        )
        service.get_target_node_names_for_text.side_effect = RuntimeError("target failure")

    result = aegis_rules._build_workflow_impact_test(
        service, object(), "target-rule", "rule text"
    )

    assert result.passed is False
    expected = "IMPORT_TREE_FAILED" if failure == "imports" else "TARGET_EXTRACTION_FAILED"
    assert expected in {item.code for item in result.diagnostics}


def test_rule_and_workflow_reference_rewriters_cover_nested_bindings(monkeypatch):
    node = {
        "ruleName": "old",
        "policyRuleName": "old",
        "policyBinding": {"ruleSetName": "old", "ruleRef": "other"},
    }
    assert aegis_rules._set_node_rule_name(node, "old", "new") is True
    assert node["ruleName"] == "new"
    assert node["policyRuleName"] == "new"
    assert node["policyBinding"]["ruleSetName"] == "new"
    assert aegis_rules._rewrite_direct_import_name("IMPORT: old\nvalue", "old", "new") == "IMPORT: new\nvalue"

    service = MagicMock()
    service.list_rules.return_value = [
        {},
        {"name": "new"},
        {"name": "unreadable"},
        {"name": "unchanged"},
        {"name": "importer"},
    ]
    service.get_rule_text.side_effect = [
        LookupError("missing"),
        "value",
        "IMPORT: old\nvalue",
    ]
    service.get_latest_rule_file.return_value = SimpleNamespace(file_id=9)
    monkeypatch.setattr(
        aegis_rules,
        "build_policy_integrity",
        lambda *_args: {"ruleVersionHash": "rule-hash", "importTreeHash": "tree-hash"},
    )

    updates = aegis_rules._rewrite_rule_import_references(service, "old", "new")

    assert len(updates) == 1
    assert updates[0].ruleName == "importer"
    service.create_rule_file.assert_called_once_with("importer", "IMPORT: new\nvalue")
    assert aegis_rules._rewrite_rule_import_references(service, "same", "same") == []


def test_workflow_reference_rewriter_skips_unusable_definitions(monkeypatch):
    repository = MagicMock()
    repository.list_definitions.return_value = [
        {},
        {"id": "no-version"},
        {"id": "bad-version"},
        {"id": "no-matches"},
    ]
    repository.get_latest_version.side_effect = [
        None,
        {"definition": []},
        {
            "definition": {
                "nodes": [
                    {"id": "other", "type": "OTHER", "ruleName": "old"},
                    {"id": "unchanged", "type": "RULE_GATE", "ruleName": "different"},
                ]
            }
        },
    ]
    monkeypatch.setattr(aegis_rules, "AegisWorkflowRepository", lambda db: repository)
    monkeypatch.setattr(aegis_rules, "AegisWorkflowAuthoringService", MagicMock())

    assert aegis_rules._rewrite_workflow_rule_references(
        object(), MagicMock(), "old", "new"
    ) == []


def test_invalid_rule_guard_returns_for_valid_and_raises_with_details():
    service = MagicMock()
    service.validate_draft_rule.return_value = SimpleNamespace(valid=True, errors=[], warnings=[])
    aegis_rules._raise_invalid_rule("rule", "text", service)

    service.validate_draft_rule.return_value = SimpleNamespace(
        valid=False,
        errors=[
            SimpleNamespace(
                code="INVALID",
                message="bad rule",
                waiver_id="waiver-invalid",
                line=2,
                node_name="goal",
            )
        ],
        warnings=[],
    )
    with pytest.raises(HTTPException) as caught:
        aegis_rules._raise_invalid_rule("rule", "bad", service)
    assert caught.value.status_code == 400
    assert caught.value.detail["validation"]["errors"][0]["code"] == "INVALID"


@pytest.mark.asyncio
async def test_graph_preview_maps_parser_failure(monkeypatch):
    service = MagicMock()
    service.get_rule_graph_data_for_text.side_effect = RuntimeError("parse failed")
    monkeypatch.setattr(aegis_rules, "_service", lambda db: service)

    with pytest.raises(HTTPException) as caught:
        await aegis_rules.preview_aegis_rule_graph(
            aegis_rules.AegisRuleGraphPreviewRequest(ruleName="rule", ruleText="text"),
            db=object(),
        )
    assert caught.value.status_code == 400


@pytest.mark.asyncio
async def test_save_and_update_validate_required_names():
    with pytest.raises(HTTPException) as save_error:
        await aegis_rules.save_aegis_rule(
            aegis_rules.SaveAegisRuleRequest(name=" ", ruleText="text"), db=object()
        )
    assert save_error.value.status_code == 400

    with pytest.raises(HTTPException) as update_error:
        await aegis_rules.update_aegis_rule(
            " ",
            aegis_rules.UpdateAegisRuleRequest(name="new", ruleText="text"),
            db=object(),
        )
    assert update_error.value.status_code == 400


@pytest.mark.asyncio
async def test_update_rule_rejects_duplicate_impact_failures_and_missing_record(monkeypatch):
    repository = MagicMock()
    service = MagicMock()
    service.get_rule_by_name.return_value = SimpleNamespace(target_node_name="old-target")
    service.get_rule_text.return_value = "same text"
    monkeypatch.setattr(aegis_rules, "AegisRuleRepositoryImpl", lambda db: repository)
    monkeypatch.setattr(aegis_rules, "RuleService", lambda repo: service)
    monkeypatch.setattr(aegis_rules, "_validate_selected_target", lambda *_args: ["new-target"])

    repository.find_id_by_name.return_value = 2
    with pytest.raises(HTTPException) as duplicate:
        await aegis_rules.update_aegis_rule(
            "old",
            aegis_rules.UpdateAegisRuleRequest(name="new", ruleText="same text"),
            db=object(),
        )
    assert duplicate.value.status_code == 409

    repository.find_id_by_name.return_value = None
    usage = _usage(_reference())
    monkeypatch.setattr(aegis_rules, "_build_workflow_usage", lambda *_args: usage)
    with pytest.raises(HTTPException) as impact_required:
        await aegis_rules.update_aegis_rule(
            "old",
            aegis_rules.UpdateAegisRuleRequest(
                name="old", ruleText="same text", targetNodeName="new-target"
            ),
            db=object(),
        )
    assert impact_required.value.status_code == 409

    failed = MagicMock(passed=False)
    failed.model_dump.return_value = {"passed": False}
    monkeypatch.setattr(aegis_rules, "_build_workflow_impact_test", lambda *_args, **_kwargs: failed)
    with pytest.raises(HTTPException) as failed_impact:
        await aegis_rules.update_aegis_rule(
            "old",
            aegis_rules.UpdateAegisRuleRequest(
                name="old",
                ruleText="same text",
                targetNodeName="new-target",
                requireWorkflowImpactPass=True,
            ),
            db=object(),
        )
    assert failed_impact.value.status_code == 409

    repository.update_rule_metadata.return_value = False
    with pytest.raises(HTTPException) as missing:
        await aegis_rules.update_aegis_rule(
            "old",
            aegis_rules.UpdateAegisRuleRequest(name="old", ruleText="same text"),
            db=object(),
        )
    assert missing.value.status_code == 404


@pytest.mark.asyncio
async def test_rule_graph_and_target_list_routes(monkeypatch):
    service = MagicMock()
    service.get_rule_by_name.return_value = SimpleNamespace(target_node_name="goal")
    service.get_rule_graph_data.return_value = {
        "rule_name": "rule",
        "source": "stored",
        "rule_text": "text",
        "expanded_rule_text": "text",
        "schema_version": 1,
        "nodes": [],
        "edges": [],
    }
    service.get_target_node_names.return_value = ["goal"]
    monkeypatch.setattr(aegis_rules, "_service", lambda db: service)

    graph = await aegis_rules.get_aegis_rule_graph("rule", db=object())
    targets = await aegis_rules.list_aegis_rule_targets("rule", db=object())

    assert graph.selectedTargetNodeName == "goal"
    assert graph.targetNodeNames == ["goal"]
    assert targets == ["goal"]


@pytest.mark.asyncio
async def test_target_update_handles_noop_failed_impact_and_missing_update(monkeypatch):
    repository = MagicMock()
    service = MagicMock()
    service.get_rule_by_name.return_value = SimpleNamespace(target_node_name="goal")
    service.get_rule_text.return_value = "text"
    monkeypatch.setattr(aegis_rules, "AegisRuleRepositoryImpl", lambda db: repository)
    monkeypatch.setattr(aegis_rules, "RuleService", lambda repo: service)
    monkeypatch.setattr(aegis_rules, "_validate_selected_target", lambda *_args: ["goal", "other"])

    with pytest.raises(HTTPException) as blank:
        await aegis_rules.update_aegis_rule_target(
            "rule",
            aegis_rules.UpdateAegisRuleTargetRequest(targetNodeName=" "),
            db=object(),
        )
    assert blank.value.status_code == 400

    unchanged = await aegis_rules.update_aegis_rule_target(
        "rule",
        aegis_rules.UpdateAegisRuleTargetRequest(targetNodeName="goal"),
        db=object(),
    )
    assert unchanged.targetNodeName == "goal"

    service.get_rule_by_name.return_value = SimpleNamespace(target_node_name="old")
    monkeypatch.setattr(aegis_rules, "_build_workflow_usage", lambda *_args: _usage())
    failed_impact = MagicMock(passed=False)
    failed_impact.model_dump.return_value = {"passed": False}
    monkeypatch.setattr(aegis_rules, "_build_workflow_impact_test", lambda *_args, **_kwargs: failed_impact)
    with pytest.raises(HTTPException) as impact_error:
        await aegis_rules.update_aegis_rule_target(
            "rule",
            aegis_rules.UpdateAegisRuleTargetRequest(
                targetNodeName="other", requireWorkflowImpactPass=True
            ),
            db=object(),
        )
    assert impact_error.value.status_code == 409

    passing = MagicMock(passed=True)
    monkeypatch.setattr(aegis_rules, "_build_workflow_impact_test", lambda *_args, **_kwargs: passing)
    repository.update_rule_target.return_value = False
    with pytest.raises(HTTPException) as missing:
        await aegis_rules.update_aegis_rule_target(
            "rule",
            aegis_rules.UpdateAegisRuleTargetRequest(
                targetNodeName="other", requireWorkflowImpactPass=True
            ),
            db=object(),
        )
    assert missing.value.status_code == 404


@pytest.mark.asyncio
async def test_rule_version_requires_passing_impact_and_builds_response(monkeypatch):
    service = MagicMock()
    service.create_rule_file.return_value = "saved text"
    service.get_latest_rule_file.return_value = SimpleNamespace(file_id=8)
    monkeypatch.setattr(aegis_rules, "_service", lambda db: service)
    failed = MagicMock(passed=False)
    failed.model_dump.return_value = {"passed": False}
    monkeypatch.setattr(aegis_rules, "_build_workflow_impact_test", lambda *_args: failed)

    with pytest.raises(HTTPException) as caught:
        await aegis_rules.create_aegis_rule_version(
            "rule",
            aegis_rules.AegisRuleVersionCreateRequest(
                ruleText="text", requireWorkflowImpactPass=True
            ),
            db=object(),
        )
    assert caught.value.status_code == 409

    monkeypatch.setattr(
        aegis_rules,
        "build_policy_integrity",
        lambda *_args: {
            "ruleVersionHash": "rule-hash",
            "importTreeHash": "tree-hash",
            "validationStatus": "valid",
        },
    )
    response = await aegis_rules.create_aegis_rule_version(
        "rule",
        aegis_rules.AegisRuleVersionCreateRequest(ruleText="text"),
        db=object(),
    )
    assert response.latest_file_id == 8
    assert response.ruleVersionHash == "rule-hash"

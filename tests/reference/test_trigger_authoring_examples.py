import json
from pathlib import Path
from unittest.mock import MagicMock

from src.domain.models.rule import RuleFileEntity
from src.domain.rule_parser.rule_set_parser import RuleSetParser
from src.domain.rule_parser.rule_set_reader import RuleSetReader
from src.domain.rule_parser.rule_set_scanner import RuleSetScanner
from src.ports.rule_repository_port import RuleRepositoryPort
from src.services.rule_service import RuleService


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_ROOT = ROOT / "docs" / "reference" / "examples"
CATALOG_PATH = EXAMPLE_ROOT / "authoring_catalog.json"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _catalog_examples() -> list[dict]:
    catalog = _load_json(CATALOG_PATH)
    return catalog["examples"]


def _repo_path(catalog_path: str) -> Path:
    path = (ROOT / catalog_path).resolve()
    assert path.is_relative_to(EXAMPLE_ROOT.resolve())
    assert path.exists(), f"{catalog_path} does not exist"
    return path


def _entrypoint_paths(example: dict) -> list[str]:
    return [entrypoint["path"] for entrypoint in example["entrypoints"]]


def _parse_rule_text(rule_text: str, source_name: str):
    reader = RuleSetReader()
    parser = RuleSetParser()
    parser.create()
    parser.set_source_name(source_name)
    reader.set_file_with_text(rule_text)

    scanner = RuleSetScanner(reader, parser)
    scanner.scan_rule_set()
    return scanner.establish_node_set()


def _catalog_rule_service() -> RuleService:
    rule_text_by_name = {
        path.stem: path.read_text(encoding="utf-8")
        for path in EXAMPLE_ROOT.rglob("*.txt")
    }
    repository = MagicMock(spec=RuleRepositoryPort)

    def find_rule_text(rule_name: str):
        text = rule_text_by_name.get(rule_name)
        if text is None:
            return None
        return RuleFileEntity(files=text.encode("utf-8"))

    repository.find_rule_text_by_rule_name.side_effect = find_rule_text
    return RuleService(repository)


def test_authoring_catalog_exposes_trigger_examples() -> None:
    examples = _catalog_examples()
    by_id = {example["id"]: example for example in examples}

    assert {"aegis_trigger_outcome_to_rule_set", "aegis_trigger_direct_action"} <= set(by_id)

    for example in by_id.values():
        if "trigger" not in example["featureTags"]:
            continue
        paths = _entrypoint_paths(example)
        assert "authoring_page" in example["audience"]
        assert example["authoringSurface"]["section"] == "Trigger policies"
        assert example["authoringSurface"]["recommendedPrimaryPath"] in paths
        assert example["runtime"]["policyEndpoint"] == "POST /api/v1/aegis/trigger-policies"
        for path in paths:
            _repo_path(path)


def test_trigger_rule_set_examples_validate_and_parse() -> None:
    rule_paths = {
        path
        for example in _catalog_examples()
        for path in _entrypoint_paths(example)
        if path.endswith(".txt")
    }
    service = _catalog_rule_service()

    assert rule_paths
    for catalog_path in sorted(rule_paths):
        path = _repo_path(catalog_path)
        rule_text = path.read_text(encoding="utf-8")

        report = service.validate_draft_rule(rule_text, path.stem)
        assert report.valid, [error.message for error in report.errors]

        node_set = service.build_rule_set_parser(path.stem).get_node_set()
        assert node_set.get_input_dictionary()
        assert node_set.get_node_dictionary()
        assert tuple(node_set.get_graph().all_node_names())


def test_trigger_policy_json_matches_authoring_contract() -> None:
    for example in _catalog_examples():
        if "trigger" not in example["featureTags"]:
            continue

        policy_path = next(path for path in _entrypoint_paths(example) if path.endswith("_policy.json"))
        request_path = next(path for path in _entrypoint_paths(example) if path.endswith("_request.json"))
        policy = _load_json(_repo_path(policy_path))
        request = _load_json(_repo_path(request_path))

        assert policy["mode"] in {"recommend_only", "human_approval_required", "automatic"}
        assert policy["status"] == "active"
        assert policy["source"]["type"] in {"rule_set", "direct"}
        assert policy["target"]["type"] in {"rule_set", "action"}
        assert request["policyId"] == policy["policyId"]
        assert request["idempotencyKey"]

        constraints = policy["constraints"]
        assert isinstance(constraints["maxDepth"], int)
        assert constraints["maxDepth"] > 0
        assert isinstance(constraints["confidenceThreshold"], (int, float))
        assert set(constraints["factSourceFilter"]) <= {"ASSERTED", "INFERRED", "SEMANTIC"}
        assert constraints["requiredEvidenceRefs"]

        if policy["source"]["type"] == "rule_set":
            assert request["sourceResult"]["ruleName"] == policy["source"]["ruleName"]
            assert set(constraints["requiredEvidenceRefs"]) <= set(request["sourceResult"]["evidenceRefs"])
            assert request["actor"]["role"] == "workflow runtime"
        else:
            assert policy["source"]["eventType"]
            assert set(constraints["requiredEvidenceRefs"]) <= set(request["evidenceRefs"])
            assert request["actor"]["role"] == "operator"

        if policy["target"]["type"] == "rule_set":
            target_path = next(
                path for path in _entrypoint_paths(example) if path.endswith("_target_eligibility.txt")
            )
            target_text = _repo_path(target_path).read_text(encoding="utf-8")
            target_node_set = _parse_rule_text(target_text, policy["target"]["ruleName"])
            assert policy["target"]["targetNodeName"] in target_node_set.get_node_dictionary()
        else:
            action = policy["target"]["action"]
            assert action["kind"]
            assert action["target"]
            assert example["runtime"]["expectedExecutionType"] == "action"

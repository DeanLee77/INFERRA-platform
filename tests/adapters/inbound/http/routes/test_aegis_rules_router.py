from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.domain.models.rule import RuleEntity, RuleFileEntity
from src.main import app


AEGIS_RULE_TEXT = """INPUT age AS NUMBER

eligible
    AND age >= 18
"""

AXIOM_RULE_TEXT = """INPUT age AS NUMBER

legacy eligible
    AND age >= 99
"""

COMMON_RULE_TEXT = """INPUT imported age AS NUMBER
FIXED minimum imported age IS 18
"""

ROOT_WITH_IMPORT_TEXT = """IMPORT: common_rule

eligible for imported benefit
    AND imported age >= minimum imported age
"""


class MemoryRuleRepository:
    def __init__(self) -> None:
        self._rules: dict[str, RuleEntity] = {}
        self._files: dict[str, list[RuleFileEntity]] = {}
        self._histories: dict[str, list[dict]] = {}
        self._next_rule_id = 1
        self._next_file_id = 1

    def seed(self, name: str, rule_text: str, category: str = "Test", description: str = "") -> None:
        rule_id = self.create_rule(
            {
                "rule_name": name,
                "rule_category": category,
                "rule_description": description,
            }
        )
        self.create_rule_file(rule_id, bytearray(rule_text.encode("utf-8")))

    def _name_by_id(self, rule_id: int) -> str:
        for name, rule in self._rules.items():
            if rule.rule_id == rule_id:
                return name
        raise LookupError(f"Rule id '{rule_id}' was not found")

    def find_id_by_name(self, rule_name: str):
        rule = self._rules.get(rule_name)
        return rule.rule_id if rule else None

    def find_rule_by_rule_name(self, rule_name: str):
        return self._rules.get(rule_name)

    def find_rule_text_by_rule_name(self, rule_name: str):
        files = self._files.get(rule_name, [])
        return files[-1] if files else None

    def find_all_rules(self):
        return [
            {
                "rule_id": rule.rule_id,
                "name": rule.name,
                "category": rule.category,
                "description": rule.description,
                "targetNodeName": rule.target_node_name,
            }
            for rule in self._rules.values()
        ]

    def update_rule_name_and_category(self, old_rule_name: str, new_rule_name: str, new_category: str) -> bool:
        rule = self._rules.pop(old_rule_name, None)
        if rule is None:
            return False
        rule.name = new_rule_name
        rule.category = new_category
        self._rules[new_rule_name] = rule
        self._files[new_rule_name] = self._files.pop(old_rule_name, [])
        self._histories[new_rule_name] = self._histories.pop(old_rule_name, [])
        return True

    def update_rule_metadata(
        self,
        old_rule_name: str,
        new_rule_name: str,
        new_category: str,
        new_description: str,
        target_node_name: str | None = None,
        update_target: bool = False,
    ) -> bool:
        rule = self._rules.pop(old_rule_name, None)
        if rule is None:
            return False
        rule.name = new_rule_name
        rule.category = new_category
        rule.description = new_description
        if update_target:
            rule.target_node_name = target_node_name
        self._rules[new_rule_name] = rule
        self._files[new_rule_name] = self._files.pop(old_rule_name, [])
        self._histories[new_rule_name] = self._histories.pop(old_rule_name, [])
        return True

    def update_rule_target(self, rule_name: str, target_node_name: str) -> bool:
        rule = self._rules.get(rule_name)
        if rule is None:
            return False
        rule.target_node_name = target_node_name
        return True

    def create_rule(self, rule_details: dict) -> int:
        name = rule_details["rule_name"]
        existing = self.find_id_by_name(name)
        if existing is not None:
            rule = self._rules[name]
            rule.category = rule_details.get("rule_category")
            rule.description = rule_details.get("rule_description")
            if "target_node_name" in rule_details:
                rule.target_node_name = rule_details.get("target_node_name")
            return existing
        rule_id = self._next_rule_id
        self._next_rule_id += 1
        self._rules[name] = RuleEntity(
            rule_id=rule_id,
            name=name,
            category=rule_details.get("rule_category"),
            description=rule_details.get("rule_description"),
            target_node_name=rule_details.get("target_node_name"),
        )
        return rule_id

    def create_rule_file(self, rule_id: int, new_file: bytearray) -> None:
        name = self._name_by_id(rule_id)
        file_id = self._next_file_id
        self._next_file_id += 1
        self._files.setdefault(name, []).append(
            RuleFileEntity(
                file_id=file_id,
                rule_id=rule_id,
                files=bytes(new_file),
            )
        )

    def create_rule_history(self, rule_id: int, history: dict) -> None:
        self._histories.setdefault(self._name_by_id(rule_id), []).append(history)

    def find_rule_by_rule_name_with_latest_history(self, rule_name: str):
        rule = self._rules.get(rule_name)
        if rule is None:
            return None
        histories = self._histories.get(rule_name, [])
        return {"rule": rule, "history": histories[-1] if histories else None}


@pytest.fixture
def repos():
    return MemoryRuleRepository(), MemoryRuleRepository()


@pytest.fixture
def client(repos):
    aegis_repo, shared_repo = repos

    from src.adapters.inbound.http.dependencies import get_aegis_db_session, get_db_session

    def _override_db():
        yield MagicMock()

    app.dependency_overrides[get_aegis_db_session] = _override_db
    app.dependency_overrides[get_db_session] = _override_db

    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "src.adapters.inbound.http.routes.aegis_rules.AegisRuleRepositoryImpl",
                return_value=aegis_repo,
            )
        )
        stack.enter_context(
            patch(
                "src.adapters.inbound.http.routes.aegis.AegisRuleRepositoryImpl",
                return_value=aegis_repo,
            )
        )
        stack.enter_context(
            patch(
                "src.adapters.inbound.http.routes.aegis.get_aegis_db",
                _override_db,
            )
        )
        stack.enter_context(
            patch(
                "src.adapters.inbound.http.routes.rules.RuleRepositoryImpl",
                return_value=shared_repo,
            )
        )
        with TestClient(app) as test_client:
            yield test_client

    app.dependency_overrides.clear()


def test_aegis_rule_routes_do_not_return_shared_same_name_rule(client, repos):
    aegis_repo, shared_repo = repos
    shared_repo.seed("collision_rule", AXIOM_RULE_TEXT, category="AXIOM")

    response = client.post(
        "/api/v1/aegis/rules",
        json={
            "name": "collision_rule",
            "category": "AEGIS",
            "description": "AEGIS-owned policy",
            "ruleText": AEGIS_RULE_TEXT,
        },
    )

    assert response.status_code == 201
    assert response.json()["store"] == "aegis-rule-store"

    aegis_response = client.get("/api/v1/aegis/rules/collision_rule/text")
    assert aegis_response.status_code == 200
    assert aegis_response.json()["ruleText"] == AEGIS_RULE_TEXT
    assert aegis_response.json()["product"] == "AEGIS"

    shared_response = client.get("/api/v1/rules/collision_rule")
    assert shared_response.status_code == 200
    assert shared_response.json()["rule_text"] == AXIOM_RULE_TEXT
    assert aegis_repo.find_rule_text_by_rule_name("collision_rule").files != shared_repo.find_rule_text_by_rule_name(
        "collision_rule"
    ).files


def test_aegis_list_excludes_shared_only_rules(client, repos):
    aegis_repo, shared_repo = repos
    shared_repo.seed("shared_only", AXIOM_RULE_TEXT)
    aegis_repo.seed("aegis_only", AEGIS_RULE_TEXT)

    response = client.get("/api/v1/aegis/rules")

    assert response.status_code == 200
    names = {rule["name"] for rule in response.json()}
    assert names == {"aegis_only"}


def test_aegis_validate_imports_fail_closed_without_shared_fallback(client, repos):
    _, shared_repo = repos
    shared_repo.seed("common_rule", COMMON_RULE_TEXT)

    response = client.post(
        "/api/v1/aegis/rules/validate",
        json={
            "rule_name": "root_rule",
            "rule_text": ROOT_WITH_IMPORT_TEXT,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert any(error["code"] == "UNRESOLVED_IMPORT" for error in data["errors"])
    assert any(error["node_name"] == "common_rule" for error in data["errors"])


def test_aegis_imports_resolve_from_aegis_store(client, repos):
    aegis_repo, _ = repos
    aegis_repo.seed("common_rule", COMMON_RULE_TEXT)
    aegis_repo.seed("root_rule", ROOT_WITH_IMPORT_TEXT)

    validation_response = client.post(
        "/api/v1/aegis/rules/validate",
        json={
            "rule_name": "root_rule",
            "rule_text": ROOT_WITH_IMPORT_TEXT,
        },
    )
    import_response = client.get("/api/v1/aegis/rules/root_rule/imports")

    assert validation_response.status_code == 200
    assert validation_response.json()["valid"] is True
    assert import_response.status_code == 200
    data = import_response.json()
    assert data["store"] == "aegis-rule-store"
    assert data["missing"] == []
    assert data["imports"][0]["name"] == "common_rule"
    assert data["importTreeHash"].startswith("sha256:")


def test_aegis_graph_preview_and_create_persist_target_metadata(client):
    preview_response = client.post(
        "/api/v1/aegis/rules/graph-preview",
        json={"ruleName": "new_aegis_rule", "ruleText": AEGIS_RULE_TEXT},
    )
    create_response = client.post(
        "/api/v1/aegis/rules",
        json={
            "name": "new_aegis_rule",
            "category": "AEGIS",
            "description": "Rule with selected target.",
            "ruleText": AEGIS_RULE_TEXT,
            "targetNodeName": "eligible",
            "createOnly": True,
        },
    )
    detail_response = client.get("/api/v1/aegis/rules/new_aegis_rule")
    list_response = client.get("/api/v1/aegis/rules")

    assert preview_response.status_code == 200
    preview = preview_response.json()
    child_target = next(
        node["name"]
        for node in preview["nodes"]
        if node["name"] not in preview["targetNodeNames"]
    )
    child_create_response = client.post(
        "/api/v1/aegis/rules",
        json={
            "name": "new_aegis_child_target_rule",
            "category": "AEGIS",
            "description": "Rule with a dependency node selected as target.",
            "ruleText": AEGIS_RULE_TEXT,
            "targetNodeName": child_target,
            "createOnly": True,
        },
    )
    child_detail_response = client.get("/api/v1/aegis/rules/new_aegis_child_target_rule")

    assert preview["source"] == "draft"
    assert preview["targetNodeNames"] == ["eligible"]
    assert create_response.status_code == 201
    assert create_response.json()["targetNodeName"] == "eligible"
    assert detail_response.status_code == 200
    assert detail_response.json()["targetNodeName"] == "eligible"
    assert list_response.status_code == 200
    assert next(
        rule
        for rule in list_response.json()
        if rule["name"] == "new_aegis_rule"
    )["targetNodeName"] == "eligible"
    assert child_create_response.status_code == 201
    assert child_create_response.json()["targetNodeName"] == child_target
    assert child_detail_response.status_code == 200
    assert child_detail_response.json()["targetNodeName"] == child_target


def test_aegis_gate_evaluation_loads_persisted_rule_and_hashes(client, repos):
    aegis_repo, shared_repo = repos
    aegis_repo.seed("collision_rule", AEGIS_RULE_TEXT)
    shared_repo.seed("collision_rule", AXIOM_RULE_TEXT)

    response = client.post("/api/v1/aegis/gates/evaluate", json={"ruleName": "collision_rule"})

    assert response.status_code == 200
    data = response.json()
    assert data["product"] == "AEGIS"
    assert data["store"] == "aegis-rule-store"
    assert data["ruleName"] == "collision_rule"
    assert data["targetNodeName"] == "eligible"
    assert data["ruleVersionHash"].startswith("sha256:")
    assert data["importTreeHash"].startswith("sha256:")
    assert data["policyIntegrity"]["store"] == "aegis-rule-store"
    assert data["convergenceState"] == "POLICY_READY"


def test_aegis_gate_and_inference_do_not_fallback_to_shared_store(client, repos):
    _, shared_repo = repos
    shared_repo.seed("shared_only", AXIOM_RULE_TEXT)

    gate_response = client.post("/api/v1/aegis/gates/evaluate", json={"ruleName": "shared_only"})
    session_response = client.post(
        "/api/v1/aegis/inference/sessions",
        json={"rule_name": "shared_only", "target_node_name": "legacy eligible"},
    )

    assert gate_response.status_code == 404
    assert session_response.status_code == 404

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.adapters.outbound.ontology.inferra_to_rdf_compiler import COMPILER_VERSION
from src.domain.models.rule import RuleEntity, RuleFileEntity
from src.main import app


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def client(mock_db):
    from src.adapters.inbound.http.dependencies import get_db_session

    def _override():
        yield mock_db

    app.dependency_overrides[get_db_session] = _override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


class TestRulesV1Router:
    @patch("src.services.rule_service.RuleService.list_rules")
    def test_list_rule_sets_uses_modern_field_names(self, mock_list, client):
        mock_list.return_value = [
            {
                "rule_id": 1,
                "name": "benefit_eligibility_v1",
                "category": "Benefits",
                "description": "Eligibility rules",
            }
        ]

        response = client.get("/api/v1/rules")

        assert response.status_code == 200
        assert response.json() == [
            {
                "rule_id": 1,
                "rule_name": "benefit_eligibility_v1",
                "category": "Benefits",
                "description": "Eligibility rules",
            }
        ]

    @patch("src.services.rule_service.RuleService.get_latest_rule_file")
    @patch("src.services.rule_service.RuleService.get_rule_by_name")
    @patch("src.services.rule_service.RuleService.save_converted_rule")
    def test_create_rule_set_saves_and_returns_detail(
        self,
        mock_save,
        mock_get_rule,
        mock_get_file,
        client,
    ):
        mock_get_rule.return_value = RuleEntity(
            rule_id=7,
            name="benefit_eligibility_v1",
            category="Benefits",
            description="Eligibility rules",
        )
        mock_get_file.return_value = RuleFileEntity(
            file_id=11,
            rule_id=7,
            files=b"INPUT age AS NUMBER\nage > 18\n",
        )

        response = client.post(
            "/api/v1/rules",
            json={
                "rule_name": "benefit_eligibility_v1",
                "category": "Benefits",
                "description": "Eligibility rules",
                "rule_text": "INPUT age AS NUMBER\nage > 18\n",
                "waived_error_ids": ["TYPE_MISMATCH:age"],
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["rule_name"] == "benefit_eligibility_v1"
        assert data["rule_text"] == "INPUT age AS NUMBER\nage > 18\n"
        assert data["latest_file_id"] == 11
        mock_save.assert_called_once_with(
            "benefit_eligibility_v1",
            "Benefits",
            "Eligibility rules",
            "INPUT age AS NUMBER\nage > 18\n",
            waived_error_ids=["TYPE_MISMATCH:age"],
        )

    @patch("src.services.rule_service.RuleService.get_latest_rule_file")
    @patch("src.services.rule_service.RuleService.get_rule_by_name")
    def test_get_rule_set_returns_latest_rule_text(self, mock_get_rule, mock_get_file, client):
        mock_get_rule.return_value = RuleEntity(
            rule_id=7,
            name="benefit_eligibility_v1",
            category="Benefits",
            description="Eligibility rules",
        )
        mock_get_file.return_value = RuleFileEntity(
            file_id=11,
            rule_id=7,
            files=b"INPUT age AS NUMBER\nage > 18\n",
        )

        response = client.get("/api/v1/rules/benefit_eligibility_v1")

        assert response.status_code == 200
        assert response.json() == {
            "rule_id": 7,
            "rule_name": "benefit_eligibility_v1",
            "category": "Benefits",
            "description": "Eligibility rules",
            "rule_text": "INPUT age AS NUMBER\nage > 18\n",
            "latest_file_id": 11,
        }

    @patch("src.services.rule_service.RuleService.get_rule_graph_data")
    def test_get_rule_set_graph_returns_backend_graph_payload(self, mock_get_graph, client):
        mock_get_graph.return_value = {
            "rule_name": "benefit_eligibility_v1",
            "source": "stored",
            "rule_text": "INPUT age AS NUMBER\nage > 18\n",
            "expanded_rule_text": "INPUT age AS NUMBER\nage > 18\n",
            "schema_version": 1,
            "nodes": [{"name": "age > 18", "runtime_id": 0}],
            "edges": [],
        }

        response = client.get("/api/v1/rules/benefit_eligibility_v1/graph")

        assert response.status_code == 200
        assert response.json() == {
            "rule_name": "benefit_eligibility_v1",
            "source": "stored",
            "rule_text": "INPUT age AS NUMBER\nage > 18\n",
            "expanded_rule_text": "INPUT age AS NUMBER\nage > 18\n",
            "schema_version": 1,
            "nodes": [
                {
                    "name": "age > 18",
                    "stable_id": None,
                    "runtime_id": 0,
                    "module": None,
                    "import_namespace": None,
                    "import_version": None,
                    "imported": None,
                    "import_depth": None,
                }
            ],
            "edges": [],
        }
        mock_get_graph.assert_called_once_with("benefit_eligibility_v1")

    @patch("src.services.rule_service.RuleService.get_rule_ontology_data")
    def test_get_rule_set_ontology_returns_rdf_graph_payload(self, mock_get_ontology, client):
        mock_get_ontology.return_value = {
            "rule_name": "benefit_eligibility_v1",
            "source": "compiled",
            "triple_count": 1,
            "source_hash": "hash1",
            "compiler_version": COMPILER_VERSION,
            "compiled_triple_count": 1,
            "stored_triple_count": 1,
            "graph_uri": "http://inferra.ai/schema#projection/rule/benefit",
            "sync_status": "current",
            "sync_timestamp": "2026-06-02T00:00:00Z",
            "dead_letter_visible": False,
            "integrity_status": "pass",
            "triples": [
                {
                    "subject": "http://inferra.ai/schema#rule/benefit",
                    "predicate": "http://inferra.ai/schema#name",
                    "object": "benefit",
                }
            ],
            "nodes": [
                {
                    "uri": "http://inferra.ai/schema#rule/benefit",
                    "name": "benefit",
                    "types": ["http://inferra.ai/schema#RuleSet"],
                }
            ],
            "edges": [],
        }

        response = client.get("/api/v1/rules/benefit_eligibility_v1/ontology")

        assert response.status_code == 200
        assert response.json()["triple_count"] == 1
        assert response.json()["source_hash"] == "hash1"
        assert response.json()["sync_status"] == "current"
        assert response.json()["integrity_status"] == "pass"
        assert response.json()["nodes"][0]["name"] == "benefit"
        mock_get_ontology.assert_called_once_with("benefit_eligibility_v1")

    @patch("src.services.rule_service.RuleService.get_rule_ontology_artifact")
    def test_get_rule_set_ontology_artifact_returns_named_turtle_artifact(self, mock_get_artifact, client):
        rdflib = pytest.importorskip("rdflib")
        turtle = """
            @prefix inf: <http://inferra.ai/schema#> .
            inf:artifact inf:name "drca_part_ii_ontology.ttl" .
        """
        mock_get_artifact.return_value = {
            "artifact_name": "drca_part_ii_ontology.ttl",
            "artifact_kind": "rule_set",
            "media_type": "text/turtle",
            "rule_name": "drca_part_ii_sections_14_to_33",
            "graph_uri": "http://inferra.ai/schema#projection/rule/drca_part_ii_sections_14_to_33",
            "projection_graph_uri": "http://inferra.ai/schema#projection/rule/drca_part_ii_sections_14_to_33",
            "source_hash": "hash1",
            "compiler_version": COMPILER_VERSION,
            "triple_count": 1,
            "artifact_uri": "http://inferra.ai/schema#artifact/rule-set/drca_part_ii_ontology.ttl",
            "download_url": "/api/v1/rules/drca_part_ii_sections_14_to_33/ontology/artifact/download",
            "session_id": None,
            "case_name": None,
            "target_node_name": None,
            "deterministic_outcome_ref": None,
            "turtle": turtle,
        }

        response = client.get("/api/v1/rules/drca_part_ii_sections_14_to_33/ontology/artifact")

        assert response.status_code == 200
        data = response.json()
        assert data["artifact_name"] == "drca_part_ii_ontology.ttl"
        assert data["graph_uri"].endswith("/drca_part_ii_sections_14_to_33")
        rdflib.Graph().parse(data=data["turtle"], format="turtle")
        mock_get_artifact.assert_called_once_with("drca_part_ii_sections_14_to_33")

    @patch("src.services.rule_service.RuleService.get_rule_ontology_artifact")
    def test_download_rule_set_ontology_artifact_returns_text_turtle(self, mock_get_artifact, client):
        mock_get_artifact.return_value = {
            "artifact_name": "drca_part_ii_ontology.ttl",
            "artifact_kind": "rule_set",
            "media_type": "text/turtle",
            "rule_name": "drca_part_ii_sections_14_to_33",
            "graph_uri": "http://inferra.ai/schema#projection/rule/drca_part_ii_sections_14_to_33",
            "projection_graph_uri": "http://inferra.ai/schema#projection/rule/drca_part_ii_sections_14_to_33",
            "source_hash": "hash1",
            "compiler_version": COMPILER_VERSION,
            "triple_count": 1,
            "artifact_uri": "http://inferra.ai/schema#artifact/rule-set/drca_part_ii_ontology.ttl",
            "download_url": "/api/v1/rules/drca_part_ii_sections_14_to_33/ontology/artifact/download",
            "session_id": None,
            "case_name": None,
            "target_node_name": None,
            "deterministic_outcome_ref": None,
            "turtle": '@prefix inf: <http://inferra.ai/schema#> .\ninf:artifact inf:name "drca_part_ii_ontology.ttl" .\n',
        }

        response = client.get("/api/v1/rules/drca_part_ii_sections_14_to_33/ontology/artifact/download")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/turtle")
        assert 'filename="drca_part_ii_ontology.ttl"' in response.headers["content-disposition"]
        assert "drca_part_ii_ontology.ttl" in response.text
        mock_get_artifact.assert_called_once_with("drca_part_ii_sections_14_to_33")

    @patch("src.services.rule_service.RuleService.sync_rule_ontology")
    def test_sync_rule_set_ontology_publishes_projection(self, mock_sync, client):
        mock_sync.return_value = {
            "rule_name": "benefit_eligibility_v1",
            "status": "published",
            "sync_status": "syncing",
            "task_id": "task-1",
            "triple_count": 7,
            "source_hash": "hash1",
            "compiler_version": COMPILER_VERSION,
            "compiled_triple_count": 7,
            "stored_triple_count": None,
            "graph_uri": "http://inferra.ai/schema#projection/rule/benefit_eligibility_v1",
        }

        response = client.post("/api/v1/rules/benefit_eligibility_v1/ontology/sync")

        assert response.status_code == 200
        assert response.json() == {
            "rule_name": "benefit_eligibility_v1",
            "status": "published",
            "sync_status": "syncing",
            "task_id": "task-1",
            "triple_count": 7,
            "source_hash": "hash1",
            "compiler_version": COMPILER_VERSION,
            "compiled_triple_count": 7,
            "stored_triple_count": None,
            "graph_uri": "http://inferra.ai/schema#projection/rule/benefit_eligibility_v1",
            "last_error_code": None,
            "last_error_summary": None,
        }
        mock_sync.assert_called_once_with("benefit_eligibility_v1")

    @patch("src.services.rule_service.RuleService.sync_rule_collection_ontology")
    def test_sync_rule_set_collection_ontology_publishes_import_closure(self, mock_sync, client):
        mock_sync.return_value = {
            "status": "published",
            "requested_count": 2,
            "published_count": 2,
            "skipped_count": 0,
            "failed_count": 0,
            "items": [
                {
                    "rule_name": "root",
                    "status": "published",
                    "sync_status": "syncing",
                    "task_id": "task-root",
                    "triple_count": 3,
                    "source_hash": "hash-root",
                    "compiler_version": COMPILER_VERSION,
                    "compiled_triple_count": 3,
                    "stored_triple_count": None,
                    "graph_uri": "http://inferra.ai/schema#projection/rule/root",
                },
                {
                    "rule_name": "imported",
                    "status": "published",
                    "sync_status": "syncing",
                    "task_id": "task-imported",
                    "triple_count": 2,
                    "source_hash": "hash-imported",
                    "compiler_version": COMPILER_VERSION,
                    "compiled_triple_count": 2,
                    "stored_triple_count": None,
                    "graph_uri": "http://inferra.ai/schema#projection/rule/imported",
                },
            ],
        }

        response = client.post("/api/v1/rules/root/ontology/sync-collection")

        assert response.status_code == 200
        assert response.json()["requested_count"] == 2
        assert response.json()["items"][0]["sync_status"] == "syncing"
        mock_sync.assert_called_once_with("root")

    @patch("src.services.rule_service.RuleService.sync_all_rule_ontologies")
    def test_sync_all_rule_set_ontologies_publishes_batch(self, mock_sync, client):
        mock_sync.return_value = {
            "status": "skipped",
            "requested_count": 1,
            "published_count": 0,
            "skipped_count": 1,
            "failed_count": 0,
            "items": [
                {
                    "rule_name": "root",
                    "status": "skipped",
                    "sync_status": "unknown",
                    "task_id": None,
                    "triple_count": 3,
                    "source_hash": "hash-root",
                    "compiler_version": COMPILER_VERSION,
                    "compiled_triple_count": 3,
                    "stored_triple_count": None,
                    "graph_uri": "http://inferra.ai/schema#projection/rule/root",
                }
            ],
        }

        response = client.post("/api/v1/rules/ontology/sync-all")

        assert response.status_code == 200
        assert response.json()["status"] == "skipped"
        assert response.json()["skipped_count"] == 1
        mock_sync.assert_called_once_with()

    @patch("src.services.rule_service.RuleService.get_latest_rule_file")
    @patch("src.services.rule_service.RuleService.create_rule_file")
    def test_create_rule_set_version_adds_new_file(
        self,
        mock_create_file,
        mock_get_file,
        client,
    ):
        mock_create_file.return_value = "INPUT age AS NUMBER\nage > 21\n"
        mock_get_file.return_value = RuleFileEntity(
            file_id=12,
            rule_id=7,
            files=b"INPUT age AS NUMBER\nage > 21\n",
        )

        response = client.post(
            "/api/v1/rules/benefit_eligibility_v1/versions",
            json={
                "rule_text": "INPUT age AS NUMBER\nage > 21\n",
                "waived_error_ids": ["TYPE_MISMATCH:age"],
            },
        )

        assert response.status_code == 201
        assert response.json() == {
            "rule_name": "benefit_eligibility_v1",
            "rule_text": "INPUT age AS NUMBER\nage > 21\n",
            "latest_file_id": 12,
        }
        mock_create_file.assert_called_once_with(
            "benefit_eligibility_v1",
            "INPUT age AS NUMBER\nage > 21\n",
            waived_error_ids=["TYPE_MISMATCH:age"],
        )

    @patch("src.services.rule_service.RuleService.get_target_node_names")
    def test_list_rule_set_targets(self, mock_targets, client):
        mock_targets.return_value = ["eligible for benefit"]

        response = client.get("/api/v1/rules/benefit_eligibility_v1/targets")

        assert response.status_code == 200
        assert response.json() == ["eligible for benefit"]

    def test_create_rule_set_requires_snake_case_contract(self, client):
        response = client.post(
            "/api/v1/rules",
            json={
                "ruleName": "legacy_style",
                "ruleText": "INPUT age AS NUMBER\nage > 18\n",
            },
        )

        assert response.status_code == 422

    def test_validation_endpoint_is_not_shadowed_by_rule_resource_routes(self, client):
        response = client.post(
            "/api/v1/rules/validate",
            json={
                "rule_name": "benefit_eligibility_v1",
                "rule_text": "INPUT age AS NUMBER\nage > 18\n",
            },
        )

        assert response.status_code == 200
        assert "valid" in response.json()

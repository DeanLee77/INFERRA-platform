"""
Integration tests for the inference router.

Covers session lifecycle, question/answer flow, summary pagination,
idempotency, and error handling using FastAPI TestClient with
dependency overrides.
"""

import json
from pathlib import Path

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from src.main import app
from src.adapters.outbound.session.in_memory_session_store import InMemorySessionStore
from src.domain.exceptions import ConcurrentModificationError
from src.domain.fact_values import FactValue, FactValueType
from src.domain.session import InferenceContext
from src.domain.session.session_manager import ConvergenceResult
from src.domain.state.fact_source import FactSource
from src.domain.state.feature_flags import FeatureFlags
from src.domain.inference.session import InferenceSession
from src.domain.inference.session_service import InferenceSessionService
from src.domain.inference.assessment_state import AssessmentState
from src.domain.nodes.line_type import LineType
from src.ports.session_store_port import SessionStorePort
from src.services.rule_service import RuleService


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_session_store():
    """Create a mock session store."""
    store = MagicMock(spec=SessionStorePort)
    return store


@pytest.fixture
def mock_rule_service():
    """Create a mock rule service."""
    return MagicMock(spec=RuleService)


@pytest.fixture
def mock_session_service(mock_session_store):
    """Create a mock InferenceSessionService."""
    service = MagicMock(spec=InferenceSessionService)
    return service


@pytest.fixture
def client(mock_session_service, mock_session_store):
    """Create a test client with dependency overrides."""
    from src.adapters.inbound.http.routes.inference import (
        _session_service,
        _rule_service,
        router,
    )
    from src.adapters.inbound.http.dependencies import get_session_store

    app.dependency_overrides[get_session_store] = lambda: mock_session_store

    with patch.object(
        router, "depend", {}
    ):
        # We'll override the dependency functions via the route's Depends
        # The simplest approach: use the app's dependency_overrides
        yield TestClient(app)

    app.dependency_overrides.clear()


class TestCaseRunGraphUri:
    def test_full_semantic_profile_uses_latest_pointer_named_graph_namespace(self):
        from src.adapters.inbound.http.routes.inference import _case_run_graph_uri

        assert _case_run_graph_uri(
            "vea_part_ii_sections_5_to_6",
            "Robert Smith run 1",
            ontology_profile="full_semantic_pilot",
        ) == (
            "http://inferra.ai/schema#case-run/rule/"
            "vea_part_ii/full-semantic/Robert_Smith_run_1/latest"
        )

    def test_full_semantic_version_graph_uses_source_hash_namespace(self):
        from src.adapters.inbound.http.routes.inference import _case_run_version_graph_uri

        assert _case_run_version_graph_uri(
            "vea_part_ii_sections_5_to_6",
            "Robert Smith run 1",
            "source/hash:v1",
        ) == (
            "http://inferra.ai/schema#case-run/rule/"
            "vea_part_ii/full-semantic/Robert_Smith_run_1/version/source_hash_v1"
        )

    def test_default_profile_keeps_legacy_case_run_named_graph_namespace(self):
        from src.adapters.inbound.http.routes.inference import _case_run_graph_uri

        assert _case_run_graph_uri(
            "vea_part_ii_sections_5_to_6",
            "Robert Smith run 1",
        ) == (
            "http://inferra.ai/schema#case-run/rule/"
            "vea_part_ii/Robert_Smith_run_1"
        )


def _make_mock_session(
    session_id="test-session-123",
    rule_name="test_rule",
    target_node_name="test_goal",
    active_node_name="age",
) -> InferenceSession:
    """Build a realistic-looking mock InferenceSession."""
    assessment_state = AssessmentState()
    assessment_state.set_fact("test_goal", FactValue(True, FactValueType.BOOLEAN))

    mock_ie = MagicMock()
    mock_ie.get_assessment_state.return_value = assessment_state

    mock_assessment = MagicMock()
    mock_goal_node = MagicMock()
    mock_goal_node.get_node_name.return_value = target_node_name
    mock_assessment.get_goal_node.return_value = mock_goal_node

    mock_active_node = MagicMock()
    mock_active_node.get_node_name.return_value = active_node_name
    mock_active_node.get_line_type.return_value = LineType.VALUE_CONCLUSION
    mock_assessment.get_node_to_be_asked.return_value = mock_active_node

    session = InferenceSession(
        session_id=session_id,
        rule_name=rule_name,
        target_node_name=target_node_name,
        inference_engine=mock_ie,
        assessment=mock_assessment,
    )
    return session


class _FakeFactStore:
    def __init__(self, sources_by_name):
        self._sources_by_name = sources_by_name

    def get_fact_sources(self, name):
        value = self._sources_by_name.get(name)
        if isinstance(value, Exception):
            raise value
        return value


def _auth_env(scopes: str) -> dict[str, str]:
    return {
        "INFERRA_API_KEY": "secret",
        "INFERRA_API_KEY_FILE": "",
        "INFERRA_API_KEY_SCOPES": scopes,
        "INFERRA_JWT_SECRET": "",
        "INFERRA_JWT_SECRET_FILE": "",
        "INFERRA_CSRF_PROTECTION": "false",
    }


# =============================================================================
# POST /api/v1/inference/sessions
# =============================================================================

class TestInferenceRouteScopes:
    """AuthZ coverage for inference route scopes."""

    @patch("src.domain.inference.session_service.InferenceSessionService.create_session_from_rule")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_write_route_rejects_read_only_scope(self, mock_init, mock_create):
        flags = FeatureFlags(auth_enabled=True)

        with patch(
            "src.infrastructure.auth_middleware.get_feature_flags",
            return_value=flags,
        ), patch(
            "src.adapters.inbound.http.dependencies.get_feature_flags",
            return_value=flags,
        ), patch.dict(
            "os.environ",
            _auth_env("inference:read"),
            clear=False,
        ):
            with TestClient(app) as c:
                response = c.post(
                    "/api/v1/inference/sessions",
                    headers={"x-api-key": "secret"},
                    json={
                        "rule_name": "test_rule",
                        "target_node_name": "test_goal",
                    },
                )

        assert response.status_code == 403
        assert response.json()["detail"] == "Missing required scope: inference:write"
        mock_create.assert_not_called()

    @patch("src.domain.inference.session_service.InferenceSessionService.create_session_from_rule")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_write_route_accepts_inference_write_scope(self, mock_init, mock_create):
        flags = FeatureFlags(auth_enabled=True)
        mock_create.return_value = _make_mock_session()

        with patch(
            "src.infrastructure.auth_middleware.get_feature_flags",
            return_value=flags,
        ), patch(
            "src.adapters.inbound.http.dependencies.get_feature_flags",
            return_value=flags,
        ), patch.dict(
            "os.environ",
            _auth_env("inference:write"),
            clear=False,
        ):
            with TestClient(app) as c:
                response = c.post(
                    "/api/v1/inference/sessions",
                    headers={"x-api-key": "secret"},
                    json={
                        "rule_name": "test_rule",
                        "target_node_name": "test_goal",
                    },
                )

        assert response.status_code == 200
        assert response.json()["session_id"] == "test-session-123"
        assert mock_create.call_args.kwargs["owner_id"] == "api-key"

    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_read_route_accepts_inference_read_scope(self, mock_init, mock_get):
        flags = FeatureFlags(auth_enabled=True)
        mock_get.return_value = _make_mock_session()

        with patch(
            "src.infrastructure.auth_middleware.get_feature_flags",
            return_value=flags,
        ), patch(
            "src.adapters.inbound.http.dependencies.get_feature_flags",
            return_value=flags,
        ), patch.dict(
            "os.environ",
            _auth_env("inference:read"),
            clear=False,
        ):
            with TestClient(app) as c:
                response = c.get(
                    "/api/v1/inference/summary?session_id=test-session-123",
                    headers={"x-api-key": "secret"},
                )

        assert response.status_code == 200
        assert response.json()["session_id"] == "test-session-123"


class TestCreateSession:
    """Tests for POST /api/v1/inference/sessions."""

    @patch("src.domain.inference.session_service.InferenceSessionService.create_session_from_rule")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_create_session_success(self, mock_init, mock_create):
        """Test creating a new inference session returns 200 with session details."""
        mock_session = _make_mock_session()
        mock_create.return_value = mock_session

        with TestClient(app) as c:
            response = c.post(
                "/api/v1/inference/sessions",
                json={"rule_name": "test_rule", "target_node_name": "test_goal"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "test-session-123"
        assert data["rule_name"] == "test_rule"
        assert data["target_node_name"] == "test_goal"
        assert mock_create.call_args.kwargs["use_history"] is True

    @patch("src.domain.inference.session_service.InferenceSessionService.create_session_from_rule")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_create_session_accepts_ontology_profile(self, mock_init, mock_create):
        mock_session = _make_mock_session()
        mock_session.ontology_profile = "reasoning"
        mock_create.return_value = mock_session

        with TestClient(app) as c:
            response = c.post(
                "/api/v1/inference/sessions",
                json={
                    "rule_name": "test_rule",
                    "target_node_name": "test_goal",
                    "ontology_profile": "reasoning",
                    "ontology_flags": {"auto_answer_enabled": False},
                },
            )

        assert response.status_code == 200
        assert response.json()["ontology_profile"] == "reasoning"
        assert mock_create.call_args.kwargs["ontology_profile"] == "reasoning"
        assert mock_create.call_args.kwargs["ontology_flags"] == {
            "auto_answer_enabled": False
        }

    @patch("src.domain.inference.session_service.InferenceSessionService.create_session_from_rule")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_create_session_rule_not_found(self, mock_init, mock_create):
        """Test 404 when rule does not exist."""
        mock_create.side_effect = LookupError("Rule 'missing' was not found")

        with TestClient(app) as c:
            response = c.post(
                "/api/v1/inference/sessions",
                json={"rule_name": "missing", "target_node_name": "goal"},
            )

        assert response.status_code == 404

    @patch("src.domain.inference.session_service.InferenceSessionService.create_session_from_rule")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_create_session_invalid_target(self, mock_init, mock_create):
        """Test 400 when target node doesn't exist in rule."""
        mock_create.side_effect = ValueError("Target node 'bad' does not exist")

        with TestClient(app) as c:
            response = c.post(
                "/api/v1/inference/sessions",
                json={"rule_name": "test_rule", "target_node_name": "bad"},
            )

        assert response.status_code == 400


# =============================================================================
# GET /api/v1/inference/next-question
# =============================================================================

class TestGetNextQuestion:
    """Tests for GET /api/v1/inference/next-question."""

    def test_missing_session_id_returns_422(self):
        """Test 422 when session_id is not provided."""
        with TestClient(app) as c:
            response = c.get("/api/v1/inference/next-question")
        assert response.status_code == 422

    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_session_not_found_returns_404(self, mock_init, mock_get):
        """Test 404 when session does not exist."""
        mock_get.return_value = None

        with TestClient(app) as c:
            response = c.get("/api/v1/inference/next-question?session_id=nonexistent")

        assert response.status_code == 404

    def test_next_question_with_real_engine_returns_question(self):
        """Regression: real InferenceEngine exposes question/type helpers used by the route."""
        from src.adapters.inbound.http.routes.inference import _session_service
        from src.domain.rule_parser.rule_set_parser import RuleSetParser
        from src.domain.rule_parser.rule_set_reader import RuleSetReader
        from src.domain.rule_parser.rule_set_scanner import RuleSetScanner

        rule_text = """
INPUT person agrees AS BOOLEAN

eligible
    AND person agrees
"""
        reader = RuleSetReader()
        reader.create()
        reader.set_file_with_text(rule_text)
        parser = RuleSetParser()
        parser.create()
        parser.set_source_name("test_rule")
        scanner = RuleSetScanner(reader, parser)
        scanner.scan_rule_set()
        node_set = scanner.establish_node_set()

        store = InMemorySessionStore()
        service = InferenceSessionService(store)
        session = service.create_session("test_rule", "eligible", node_set)
        app.dependency_overrides[_session_service] = lambda: service

        try:
            with TestClient(app) as c:
                response = c.get(
                    f"/api/v1/inference/next-question?session_id={session.session_id}"
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["questions"] == [
            {
                "question_text": "person agrees",
                "question_value_type": "boolean",
                "control": None,
                "options": [],
                "selection_mode": None,
                "semantic_suggestions": [],
            }
        ]
        assert data["has_more_questions"] is True

    def test_next_question_with_real_comparison_returns_lhs_question(self):
        from src.adapters.inbound.http.routes.inference import _session_service
        from src.domain.rule_parser.rule_set_parser import RuleSetParser
        from src.domain.rule_parser.rule_set_reader import RuleSetReader
        from src.domain.rule_parser.rule_set_scanner import RuleSetScanner

        rule_text = """
INPUT age AS NUMBER

eligible
    AND age >= 18
"""
        reader = RuleSetReader()
        reader.create()
        reader.set_file_with_text(rule_text)
        parser = RuleSetParser()
        parser.create()
        parser.set_source_name("test_rule")
        scanner = RuleSetScanner(reader, parser)
        scanner.scan_rule_set()
        node_set = scanner.establish_node_set()

        store = InMemorySessionStore()
        service = InferenceSessionService(store)
        session = service.create_session("test_rule", "eligible", node_set)
        app.dependency_overrides[_session_service] = lambda: service

        try:
            with TestClient(app) as c:
                response = c.get(
                    f"/api/v1/inference/next-question?session_id={session.session_id}"
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["questions"] == [
            {
                "question_text": "age",
                "question_value_type": "double",
                "control": None,
                "options": [],
                "selection_mode": None,
                "semantic_suggestions": [],
            }
        ]
        assert data["has_more_questions"] is True

    def test_next_question_with_list_input_returns_item_options(self):
        from src.adapters.inbound.http.routes.inference import _session_service
        from src.domain.rule_parser.rule_set_parser import RuleSetParser
        from src.domain.rule_parser.rule_set_reader import RuleSetReader
        from src.domain.rule_parser.rule_set_scanner import RuleSetScanner

        rule_text = """
INPUT service type AS LIST
    ITEM qualifying war service
    ITEM operational service
    ITEM peacekeeping service

eligible
    AND service type IS IN LIST: service type
"""
        reader = RuleSetReader()
        reader.create()
        reader.set_file_with_text(rule_text)
        parser = RuleSetParser()
        parser.create()
        parser.set_source_name("test_rule")
        scanner = RuleSetScanner(reader, parser)
        scanner.scan_rule_set()
        node_set = scanner.establish_node_set()

        store = InMemorySessionStore()
        service = InferenceSessionService(store)
        session = service.create_session("test_rule", "eligible", node_set)
        app.dependency_overrides[_session_service] = lambda: service

        try:
            with TestClient(app) as c:
                response = c.get(
                    f"/api/v1/inference/next-question?session_id={session.session_id}"
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["questions"] == [
            {
                "question_text": "service type",
                "question_value_type": "list",
                "control": "select",
                "options": [
                    {
                        "label": "qualifying war service",
                        "value": "qualifying war service",
                        "value_type": "string",
                    },
                    {
                        "label": "operational service",
                        "value": "operational service",
                        "value_type": "string",
                    },
                    {
                        "label": "peacekeeping service",
                        "value": "peacekeeping service",
                        "value_type": "string",
                    },
                ],
                "selection_mode": "single",
                "semantic_suggestions": [],
            }
        ]

    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_next_question_omits_semantic_suggestions_when_advisory_flag_disabled(self, mock_init, mock_get):
        session = _make_mock_session(active_node_name="incapacity status")
        session.feature_flags = FeatureFlags(ontology_advisory_enabled=False)
        session.context = InferenceContext(
            session_id=session.session_id,
            rule_name=session.rule_name,
            target=session.target_node_name,
            mandatory=[],
            fact_store=session.inference_engine.get_assessment_state.return_value.get_fact_store(),
            ontology_advisory_suggestions={
                "incapacity status": [
                    {
                        "factName": "incapacity status",
                        "suggestedValue": "current employee",
                        "sourceLabel": "SEMANTIC",
                    }
                ]
            },
        )
        active_node = session.assessment.get_node_to_be_asked.return_value
        session.inference_engine.get_next_question_with_goal_name.return_value = active_node
        session.inference_engine.find_type_of_element_to_be_asked.return_value = {
            "incapacity status": FactValueType.BOOLEAN,
        }
        session.inference_engine.get_questions_from_node_to_be_asked.return_value = [
            "incapacity status"
        ]
        mock_get.return_value = session

        with TestClient(app) as c:
            response = c.get(
                f"/api/v1/inference/next-question?session_id={session.session_id}"
            )

        assert response.status_code == 200
        assert response.json()["questions"][0]["semantic_suggestions"] == []

    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_next_question_returns_semantic_suggestions_when_advisory_flag_enabled(self, mock_init, mock_get):
        suggestion = {
            "factName": "incapacity status",
            "ontologyIri": "urn:status",
            "relationship": "inf:hasItem",
            "suggestedValue": "current employee",
            "confidence": 1.0,
            "sourceGraphUri": "urn:graph",
            "ontologySnapshotRef": "test_rule:source-hash",
            "ontologySnapshotHash": "source-hash",
            "sourceLabel": "SEMANTIC",
            "advisoryOnly": True,
            "altersDeterministicOutcome": False,
        }
        session = _make_mock_session(active_node_name="incapacity status")
        session.feature_flags = FeatureFlags(
            ontology_advisory_enabled=True,
            enriched_api=True,
        )
        session.context = InferenceContext(
            session_id=session.session_id,
            rule_name=session.rule_name,
            target=session.target_node_name,
            mandatory=[],
            fact_store=session.inference_engine.get_assessment_state.return_value.get_fact_store(),
            ontology_snapshot_ref="test_rule:source-hash",
            ontology_snapshot_hash="source-hash",
            ontology_graph_uris=["urn:graph"],
            ontology_advisory_suggestions={"incapacity status": [suggestion]},
        )
        active_node = session.assessment.get_node_to_be_asked.return_value
        session.inference_engine.get_next_question_with_goal_name.return_value = active_node
        session.inference_engine.find_type_of_element_to_be_asked.return_value = {
            "incapacity status": FactValueType.BOOLEAN,
        }
        session.inference_engine.get_questions_from_node_to_be_asked.return_value = [
            "incapacity status"
        ]
        mock_get.return_value = session

        with TestClient(app) as c:
            response = c.get(
                f"/api/v1/inference/next-question?session_id={session.session_id}"
            )

        assert response.status_code == 200
        response_suggestions = response.json()["questions"][0]["semantic_suggestions"]
        assert response_suggestions == [suggestion]
        assert response_suggestions[0]["advisoryOnly"] is True
        assert response_suggestions[0]["altersDeterministicOutcome"] is False

    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_next_question_returns_value_and_constraint_advisory_payloads(self, mock_init, mock_get):
        value_suggestion = {
            "factName": "incapacity status",
            "ontologyIri": "urn:status",
            "relationship": "inf:defaultValue",
            "suggestedValue": "current employee",
            "confidence": 0.95,
            "sourceGraphUri": "urn:graph",
            "ontologySnapshotRef": "test_rule:source-hash",
            "ontologySnapshotHash": "source-hash",
            "sourceLabel": "SEMANTIC",
            "advisoryOnly": True,
            "autoAnswerEligible": True,
            "autoAnswered": False,
            "altersDeterministicOutcome": False,
            "status": "available",
        }
        constraint_suggestion = {
            "factName": "incapacity status",
            "ontologyIri": "urn:status",
            "relationship": "rdfs:range",
            "suggestedValue": "xsd:string",
            "confidence": 1.0,
            "sourceGraphUri": "urn:graph",
            "ontologySnapshotRef": "test_rule:source-hash",
            "ontologySnapshotHash": "source-hash",
            "sourceLabel": "SEMANTIC",
            "advisoryOnly": True,
            "altersDeterministicOutcome": False,
        }
        session = _make_mock_session(active_node_name="incapacity status")
        session.feature_flags = FeatureFlags(
            ontology_advisory_enabled=True,
            enriched_api=True,
        )
        session.context = InferenceContext(
            session_id=session.session_id,
            rule_name=session.rule_name,
            target=session.target_node_name,
            mandatory=[],
            fact_store=session.inference_engine.get_assessment_state.return_value.get_fact_store(),
            ontology_value_suggestions={"incapacity status": [value_suggestion]},
            ontology_constraint_suggestions={"incapacity status": [constraint_suggestion]},
        )
        active_node = session.assessment.get_node_to_be_asked.return_value
        session.inference_engine.get_next_question_with_goal_name.return_value = active_node
        session.inference_engine.find_type_of_element_to_be_asked.return_value = {
            "incapacity status": FactValueType.BOOLEAN,
        }
        session.inference_engine.get_questions_from_node_to_be_asked.return_value = [
            "incapacity status"
        ]
        mock_get.return_value = session

        with TestClient(app) as c:
            response = c.get(
                f"/api/v1/inference/next-question?session_id={session.session_id}"
            )

        assert response.status_code == 200
        response_suggestions = response.json()["questions"][0]["semantic_suggestions"]
        assert response_suggestions == [value_suggestion, constraint_suggestion]
        assert response_suggestions[0]["autoAnswerEligible"] is True
        assert response_suggestions[1]["relationship"] == "rdfs:range"

    def test_next_question_with_iterate_skips_derived_branch_rules(self):
        """Regression: iterate OR branch rules with children are derived, not questions."""
        from src.adapters.inbound.http.routes.inference import _session_service
        from src.domain.rule_parser.rule_set_parser import RuleSetParser
        from src.domain.rule_parser.rule_set_reader import RuleSetReader
        from src.domain.rule_parser.rule_set_scanner import RuleSetScanner

        rule_text = """
FIXED allowed service types AS LIST
    ITEM warlike

INPUT service history AS LIST
    ITEM period one
    ITEM period two
INPUT service type AS LIST
    ITEM warlike

the service history meets criteria
    AND ALL service period IN service history
        OR one
            AND service type IS IN LIST: allowed service types
        OR two
            AND service type IS IN LIST: allowed service types
"""
        reader = RuleSetReader()
        reader.create()
        reader.set_file_with_text(rule_text)
        parser = RuleSetParser()
        parser.create()
        parser.set_source_name("test_rule")
        scanner = RuleSetScanner(reader, parser)
        scanner.scan_rule_set()
        node_set = scanner.establish_node_set()

        store = InMemorySessionStore()
        service = InferenceSessionService(store)
        session = service.create_session(
            "test_rule",
            "the service history meets criteria",
            node_set,
        )
        app.dependency_overrides[_session_service] = lambda: service

        try:
            with TestClient(app) as c:
                response = c.get(
                    f"/api/v1/inference/next-question?session_id={session.session_id}"
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        question_texts = [item["question_text"] for item in data["questions"]]
        assert question_texts
        assert "one" not in question_texts
        assert "two" not in question_texts
        assert question_texts[0] == "1st  service period  service type"
        assert data["iterate_progress"]["list_name"] == "service history"


# =============================================================================
# GET /api/v1/inference/summary
# =============================================================================

class TestGetSummary:
    """Tests for GET /api/v1/inference/summary — pagination + fact_source."""

    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_summary_returns_fact_source(self, mock_init, mock_get):
        """Test that summary items include fact_source provenance."""
        session = _make_mock_session()
        session.feature_flags = FeatureFlags(enriched_api=True)
        # Add a second fact so we have multiple items
        session.inference_engine.get_assessment_state().set_fact(
            "other_fact", FactValue(42, FactValueType.INTEGER)
        )
        mock_get.return_value = session

        with TestClient(app) as c:
            response = c.get("/api/v1/inference/summary?session_id=test-session-123")

        assert response.status_code == 200
        data = response.json()
        assert "summary" in data
        assert data["reasoning_mode"] == "DEDUCTION"
        assert data["confidence"] == 1.0
        assert data["status"] == "GOAL_REACHED"
        # At least one item should have a fact_source
        items_with_source = [s for s in data["summary"] if s.get("fact_source") is not None]
        assert len(items_with_source) > 0

    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_summary_pagination(self, mock_init, mock_get):
        """Test pagination via offset/limit query parameters."""
        session = _make_mock_session()
        mock_get.return_value = session

        with TestClient(app) as c:
            response = c.get(
                "/api/v1/inference/summary?session_id=test-session-123&offset=0&limit=1"
            )

        assert response.status_code == 200
        data = response.json()
        assert "total_count" in data
        assert "offset" in data
        assert "limit" in data
        assert data["limit"] == 1
        assert len(data["summary"]) <= 1

    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_summary_omits_provenance_when_enriched_api_disabled(
        self,
        mock_init,
        mock_get,
    ):
        session = _make_mock_session()
        session.feature_flags = FeatureFlags(enriched_api=False)
        session.context = InferenceContext(
            session_id=session.session_id,
            rule_name=session.rule_name,
            target=session.target_node_name,
            mandatory=[],
            fact_store=session.inference_engine.get_assessment_state().get_fact_store(),
            reasoning_mode="ABDUCTION",
            confidence=0.7,
        )
        mock_get.return_value = session

        with TestClient(app) as c:
            response = c.get(
                "/api/v1/inference/summary?session_id=test-session-123"
            )

        assert response.status_code == 200
        data = response.json()
        assert all(item["fact_source"] is None for item in data["summary"])
        assert data["reasoning_mode"] == "DEDUCTION"
        assert data["confidence"] == 1.0

    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_summary_session_not_found(self, mock_init, mock_get):
        """Test 404 when session does not exist."""
        mock_get.return_value = None

        with TestClient(app) as c:
            response = c.get("/api/v1/inference/summary?session_id=nonexistent")

        assert response.status_code == 404


# =============================================================================
# POST /api/v1/inference/feed-answer
# =============================================================================

class TestFeedAnswer:
    """Tests for POST /api/v1/inference/feed-answer — idempotency + 409."""

    def test_feed_answer_with_real_engine_materializes_derived_goal(self):
        """Answered leaf facts propagate to the parent goal returned by the API."""
        from src.adapters.inbound.http.routes.inference import _session_service
        from src.domain.rule_parser.rule_set_parser import RuleSetParser
        from src.domain.rule_parser.rule_set_reader import RuleSetReader
        from src.domain.rule_parser.rule_set_scanner import RuleSetScanner

        rule_text = """
INPUT person agrees AS BOOLEAN

eligible
    AND person agrees
"""
        reader = RuleSetReader()
        reader.create()
        reader.set_file_with_text(rule_text)
        parser = RuleSetParser()
        parser.create()
        parser.set_source_name("test_rule")
        scanner = RuleSetScanner(reader, parser)
        scanner.scan_rule_set()
        node_set = scanner.establish_node_set()

        store = InMemorySessionStore()
        service = InferenceSessionService(store)
        with patch(
            "src.domain.inference.session_service.get_feature_flags",
            return_value=FeatureFlags(enriched_api=True),
        ):
            session = service.create_session("test_rule", "eligible", node_set)
        app.dependency_overrides[_session_service] = lambda: service

        try:
            with TestClient(app) as c:
                c.get(
                    f"/api/v1/inference/next-question?session_id={session.session_id}"
                )
                response = c.post(
                    f"/api/v1/inference/feed-answer?session_id={session.session_id}",
                    json={
                        "question": "person agrees",
                        "answer": {"type": "BOOLEAN", "answer": True},
                    },
                )
                next_question = c.get(
                    f"/api/v1/inference/next-question?session_id={session.session_id}"
                )
                summary = c.get(
                    f"/api/v1/inference/summary?session_id={session.session_id}"
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        assert response.json() == {
            "has_more_questions": False,
            "goal_rule_name": "eligible",
            "goal_rule_value": "True",
            "goal_rule_type": "boolean",
        }
        assert next_question.status_code == 200
        assert next_question.json()["questions"] == []
        assert next_question.json()["has_more_questions"] is False
        assert next_question.json()["question_flow_state"] == "GOAL_REACHED"
        assert summary.status_code == 200
        assert any(
            item["node_text"] == "eligible"
            and item["node_value"] == "True"
            and item["fact_source"] == "INFERRED"
            for item in summary.json()["summary"]
        )

    def test_false_goal_reports_terminal_goal_reached(self):
        from src.adapters.inbound.http.routes.inference import _session_service
        from src.domain.rule_parser.rule_set_parser import RuleSetParser
        from src.domain.rule_parser.rule_set_reader import RuleSetReader
        from src.domain.rule_parser.rule_set_scanner import RuleSetScanner

        rule_text = """
INPUT person agrees AS BOOLEAN

eligible
    AND person agrees
"""
        reader = RuleSetReader()
        reader.create()
        reader.set_file_with_text(rule_text)
        parser = RuleSetParser()
        parser.create()
        parser.set_source_name("test_rule")
        scanner = RuleSetScanner(reader, parser)
        scanner.scan_rule_set()
        node_set = scanner.establish_node_set()

        store = InMemorySessionStore()
        service = InferenceSessionService(store)
        session = service.create_session("test_rule", "eligible", node_set)
        app.dependency_overrides[_session_service] = lambda: service

        try:
            with TestClient(app) as c:
                c.get(
                    f"/api/v1/inference/next-question?session_id={session.session_id}"
                )
                feed = c.post(
                    f"/api/v1/inference/feed-answer?session_id={session.session_id}",
                    json={
                        "question": "person agrees",
                        "answer": {"type": "BOOLEAN", "answer": False},
                    },
                )
                next_question = c.get(
                    f"/api/v1/inference/next-question?session_id={session.session_id}"
                )
        finally:
            app.dependency_overrides.clear()

        assert feed.status_code == 200
        assert feed.json() == {
            "has_more_questions": False,
            "goal_rule_name": "eligible",
            "goal_rule_value": "False",
            "goal_rule_type": "boolean",
        }
        assert next_question.status_code == 200
        data = next_question.json()
        assert data["questions"] == []
        assert data["has_more_questions"] is False
        assert data["convergence_state"] == "GOAL_REACHED"
        assert data["question_flow_state"] == "GOAL_REACHED"

    def test_false_goal_with_unresolved_sibling_mandatory_terminates(self):
        from src.adapters.inbound.http.routes.inference import _session_service
        from src.domain.rule_parser.rule_set_parser import RuleSetParser
        from src.domain.rule_parser.rule_set_reader import RuleSetReader
        from src.domain.rule_parser.rule_set_scanner import RuleSetScanner

        rule_text = """
INPUT person agrees AS BOOLEAN
INPUT venue booked AS BOOLEAN

eligible
    AND person agrees
    AND venue booked
"""
        reader = RuleSetReader()
        reader.create()
        reader.set_file_with_text(rule_text)
        parser = RuleSetParser()
        parser.create()
        parser.set_source_name("test_rule")
        scanner = RuleSetScanner(reader, parser)
        scanner.scan_rule_set()
        node_set = scanner.establish_node_set()
        node_dict = node_set.get_node_dictionary()
        node_set.set_sorted_node_list(
            [node_dict[name] for name in ["eligible", "person agrees", "venue booked"]]
        )

        store = InMemorySessionStore()
        service = InferenceSessionService(store)
        session = service.create_session("test_rule", "eligible", node_set)
        app.dependency_overrides[_session_service] = lambda: service

        try:
            with TestClient(app) as c:
                first_question = c.get(
                    f"/api/v1/inference/next-question?session_id={session.session_id}"
                )
                feed = c.post(
                    f"/api/v1/inference/feed-answer?session_id={session.session_id}",
                    json={
                        "question": "person agrees",
                        "answer": {"type": "BOOLEAN", "answer": False},
                    },
                )
                next_question = c.get(
                    f"/api/v1/inference/next-question?session_id={session.session_id}"
                )
        finally:
            app.dependency_overrides.clear()

        assert first_question.status_code == 200
        assert first_question.json()["questions"][0]["question_text"] == "person agrees"
        assert feed.status_code == 200
        assert feed.json() == {
            "has_more_questions": False,
            "goal_rule_name": "eligible",
            "goal_rule_value": "False",
            "goal_rule_type": "boolean",
        }
        assert next_question.status_code == 200
        data = next_question.json()
        assert data["questions"] == []
        assert data["has_more_questions"] is False
        assert data["convergence_state"] == "GOAL_REACHED"
        assert data["question_flow_state"] == "GOAL_REACHED"

    def test_next_question_does_not_emit_answered_stale_active_node(self):
        from src.adapters.inbound.http.routes.inference import _session_service
        from src.domain.rule_parser.rule_set_parser import RuleSetParser
        from src.domain.rule_parser.rule_set_reader import RuleSetReader
        from src.domain.rule_parser.rule_set_scanner import RuleSetScanner

        rule_text = """
INPUT person agrees AS BOOLEAN

eligible
    AND person agrees
"""
        reader = RuleSetReader()
        reader.create()
        reader.set_file_with_text(rule_text)
        parser = RuleSetParser()
        parser.create()
        parser.set_source_name("test_rule")
        scanner = RuleSetScanner(reader, parser)
        scanner.scan_rule_set()
        node_set = scanner.establish_node_set()

        store = InMemorySessionStore()
        service = InferenceSessionService(store)
        session = service.create_session("test_rule", "eligible", node_set)
        app.dependency_overrides[_session_service] = lambda: service

        try:
            with TestClient(app) as c:
                first_question = c.get(
                    f"/api/v1/inference/next-question?session_id={session.session_id}"
                )
                stale_node = session.assessment.get_node_to_be_asked()
                answer = c.post(
                    f"/api/v1/inference/feed-answer?session_id={session.session_id}",
                    json={
                        "question": "person agrees",
                        "answer": {"type": "BOOLEAN", "answer": True},
                    },
                )
                session.assessment.set_node_to_be_asked(stale_node)
                session.assessment.set_aux_node_to_be_asked(stale_node)
                response = c.get(
                    f"/api/v1/inference/next-question?session_id={session.session_id}"
                )
        finally:
            app.dependency_overrides.clear()

        assert first_question.status_code == 200
        assert first_question.json()["questions"][0]["question_text"] == "person agrees"
        assert answer.status_code == 200
        assert response.status_code == 200
        data = response.json()
        assert data["questions"] == []
        assert data["has_more_questions"] is False
        assert data["question_flow_state"] == "GOAL_REACHED"
        assert session.assessment.get_node_to_be_asked() is None
        assert session.assessment.get_aux_node_to_be_asked() is None

    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_feed_answer_duplicate_without_idempotency_key(self, mock_init, mock_get):
        """Test 409 when re-answering the same question without Idempotency-Key."""
        session = _make_mock_session()
        # Pre-populate working memory with the question already answered
        session.inference_engine.get_assessment_state().set_fact(
            "age", FactValue(25, FactValueType.INTEGER)
        )
        mock_get.return_value = session

        with TestClient(app) as c:
            # session_id must be passed as query param for _get_session_or_404 dependency
            response = c.post(
                "/api/v1/inference/feed-answer?session_id=test-session-123",
                json={
                    "question": "age",
                    "answer": {"type": "integer", "answer": 30},
                },
            )

        assert response.status_code == 409
        data = response.json()
        assert data["detail"]["error_code"] == "DUPLICATE_ANSWER"

    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_feed_answer_with_idempotency_key(self, mock_init, mock_get):
        """Test that Idempotency-Key header enables safe retries."""
        session = _make_mock_session()
        # Pre-populate so duplicate detection would normally fire
        session.inference_engine.get_assessment_state().set_fact(
            "age", FactValue(25, FactValueType.INTEGER)
        )
        mock_get.return_value = session

        with TestClient(app) as c:
            response = c.post(
                "/api/v1/inference/feed-answer?session_id=test-session-123",
                headers={"Idempotency-Key": "unique-key-2"},
                json={
                    "question": "age",
                    "answer": {"type": "integer", "answer": 30},
                },
            )

        # With an idempotency key, the request should be processed (not 409)
        # It may return 200 (processed) or 400 (bad state), but NOT 409
        assert response.status_code in (200, 400)

    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_feed_answer_session_not_found(self, mock_init, mock_get):
        """Test 404 when session does not exist."""
        mock_get.return_value = None

        with TestClient(app) as c:
            response = c.post(
                "/api/v1/inference/feed-answer?session_id=nonexistent",
                json={
                    "question": "age",
                    "answer": {"type": "integer", "answer": 25},
                },
            )

        assert response.status_code == 404

    def test_feed_answer_persists_mutated_session(self):
        from src.adapters.inbound.http.routes.inference import _session_service

        session = _make_mock_session()
        store = InMemorySessionStore()
        store.save(session)
        service = InferenceSessionService(store)
        app.dependency_overrides[_session_service] = lambda: service

        try:
            with TestClient(app) as c:
                response = c.post(
                    "/api/v1/inference/feed-answer?session_id=test-session-123",
                    json={
                        "question": "age",
                        "answer": {"type": "integer", "answer": 25},
                    },
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        assert service.get_session("test-session-123").version == 1

    def test_feed_answer_returns_409_when_session_save_conflicts(self):
        from src.adapters.inbound.http.routes.inference import _session_service

        session = _make_mock_session()

        class ConflictStore:
            def get(self, session_id):
                return session if session_id == session.session_id else None

            def save(self, _session):
                raise ConcurrentModificationError("stale session")

        service = InferenceSessionService(ConflictStore())
        app.dependency_overrides[_session_service] = lambda: service

        try:
            with TestClient(app) as c:
                response = c.post(
                    "/api/v1/inference/feed-answer?session_id=test-session-123",
                    json={
                        "question": "age",
                        "answer": {"type": "integer", "answer": 25},
                    },
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 409
        assert response.json()["detail"]["error_code"] == "SESSION_CONFLICT"


# =============================================================================
# GET /api/v1/inference/trace
# =============================================================================

class TestGetTrace:
    """Tests for PROV-O trace export."""

    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_trace_returns_turtle(self, mock_init, mock_get):
        pytest.importorskip("rdflib")
        session = _make_mock_session()
        session.feature_flags = FeatureFlags(prov_o_trace=True)
        mock_get.return_value = session

        with TestClient(app) as c:
            response = c.get("/api/v1/inference/trace?session_id=test-session-123")

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "test-session-123"
        assert data["format"] == "turtle"
        assert data["reasoning_mode"] == "DEDUCTION"
        assert "test_rule" in data["trace"]
        assert "ASSERTED" in data["trace"]

    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_trace_supports_json_ld(self, mock_init, mock_get):
        pytest.importorskip("rdflib")
        session = _make_mock_session()
        session.feature_flags = FeatureFlags(prov_o_trace=True)
        mock_get.return_value = session

        with TestClient(app) as c:
            response = c.get(
                "/api/v1/inference/trace?session_id=test-session-123&format=json-ld"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["format"] == "json-ld"
        assert "ASSERTED" in data["trace"]

    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_trace_is_unavailable_when_session_gate_is_disabled(
        self,
        mock_init,
        mock_get,
    ):
        session = _make_mock_session()
        session.feature_flags = FeatureFlags(prov_o_trace=False)
        mock_get.return_value = session

        with TestClient(app) as c:
            response = c.get(
                "/api/v1/inference/trace?session_id=test-session-123"
            )

        assert response.status_code == 503
        assert "disabled for this session" in response.json()["detail"]

    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_trace_session_not_found(self, mock_init, mock_get):
        mock_get.return_value = None

        with TestClient(app) as c:
            response = c.get("/api/v1/inference/trace?session_id=nonexistent")

        assert response.status_code == 404


# =============================================================================
# GET /api/v1/inference/ontology-artifact
# =============================================================================

class TestGetOntologyArtifact:
    """Tests for full case-run ontology artifact export."""

    def _rule_ontology(self):
        return {
            "rule_name": "drca_part_ii_sections_14_to_33",
            "source_hash": "rule-source-hash",
            "graph_uri": "http://inferra.ai/schema#projection/rule/drca_part_ii_sections_14_to_33",
            "triples": [
                {
                    "subject": "http://inferra.ai/schema#rule/drca_part_ii_sections_14_to_33",
                    "predicate": "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
                    "object": "http://inferra.ai/schema#RuleSet",
                },
                {
                    "subject": "http://inferra.ai/schema#rule/drca_part_ii_sections_14_to_33",
                    "predicate": "http://inferra.ai/schema#name",
                    "object": "drca_part_ii_sections_14_to_33",
                },
            ],
        }

    def _session(self):
        session = _make_mock_session(
            session_id="Robert-session",
            rule_name="drca_part_ii_sections_14_to_33",
            target_node_name="DRCA part II sections 14 to 33 convergence met",
        )
        state = session.inference_engine.get_assessment_state.return_value
        state.set_fact("impairment points", FactValue(5, FactValueType.INTEGER), source=FactSource.ASSERTED)
        state.set_fact("incapacity status", FactValue(["current employee"], FactValueType.LIST), source=FactSource.ASSERTED)
        state.set_fact("DRCA part II sections 14 to 33 convergence met", FactValue(True, FactValueType.BOOLEAN), source=FactSource.INFERRED)
        return session

    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_case_run_ontology_artifact_returns_named_parseable_turtle(self, mock_init, mock_get):
        rdflib = pytest.importorskip("rdflib")
        from src.adapters.inbound.http.routes.inference import _rule_service

        session = self._session()
        mock_get.return_value = session
        rule_service = MagicMock(spec=RuleService)
        rule_service.get_rule_ontology_data.return_value = self._rule_ontology()
        app.dependency_overrides[_rule_service] = lambda: rule_service

        try:
            with TestClient(app) as c:
                response = c.get(
                    "/api/v1/inference/ontology-artifact?session_id=Robert-session&case_name=Robert.json"
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["artifact_name"] == "drca_part_ii_full_ontology.ttl"
        assert data["case_name"] == "Robert.json"
        assert data["deterministic_outcome_ref"] is not None
        assert "ontology_advisory_no_rule_execution_override" in data["turtle"]
        rdflib.Graph().parse(data=data["turtle"], format="turtle")

    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_case_run_ontology_artifact_accepts_export_only_semantic_pilot_profile(
        self, mock_init, mock_get
    ):
        from src.adapters.inbound.http.routes.inference import _rule_service

        session = self._session()
        mock_get.return_value = session
        rule_service = MagicMock(spec=RuleService)
        rule_service.get_rule_ontology_data.return_value = self._rule_ontology()
        app.dependency_overrides[_rule_service] = lambda: rule_service

        try:
            with TestClient(app) as c:
                default_response = c.get(
                    "/api/v1/inference/ontology-artifact?session_id=Robert-session"
                )
                response = c.get(
                    "/api/v1/inference/ontology-artifact"
                    "?session_id=Robert-session&ontology_profile=full_semantic_pilot"
                )
        finally:
            app.dependency_overrides.clear()

        assert default_response.status_code == 200
        assert response.status_code == 200
        default_data = default_response.json()
        data = response.json()
        assert data["source_hash"] != default_data["source_hash"]
        assert data["graph_uri"] != default_data["graph_uri"]
        assert "ontology_profile=full_semantic_pilot" in data["download_url"]
        turtle = data["turtle"]
        assert "full_semantic_pilot" in turtle
        assert "export_override" in turtle
        assert "ontology_question_strategy" in turtle
        assert "ontology_reasoning" in turtle

    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_case_run_ontology_artifact_download_returns_text_turtle(self, mock_init, mock_get):
        from src.adapters.inbound.http.routes.inference import _rule_service

        session = self._session()
        mock_get.return_value = session
        rule_service = MagicMock(spec=RuleService)
        rule_service.get_rule_ontology_data.return_value = self._rule_ontology()
        app.dependency_overrides[_rule_service] = lambda: rule_service

        try:
            with TestClient(app) as c:
                response = c.get(
                    "/api/v1/inference/ontology-artifact/download?session_id=Robert-session&case_name=Robert.json"
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/turtle")
        assert 'filename="drca_part_ii_full_ontology.ttl"' in response.headers["content-disposition"]
        assert "DRCA part II sections 14 to 33 convergence met" in response.text


class TestRobertStyleVirtualOneConvergence:
    def test_public_api_converges_robert_fixture_and_exports_full_artifact(self):
        rdflib = pytest.importorskip("rdflib")
        from src.adapters.inbound.http.routes.inference import (
            _rule_service,
            _session_service,
        )
        from src.adapters.outbound.ontology.fuseki_adapter import FusekiAdapter
        from src.adapters.outbound.ontology.inferra_to_rdf_compiler import (
            InferraToRdfCompiler,
        )
        from src.domain.models.rule import RuleFileEntity
        from src.tasks.rule_sync import build_projection_source_hash

        rule_name = "drca_part_ii_sections_14_to_33"
        target_name = "DRCA part II sections 14 to 33 convergence met"
        root = Path.cwd()
        case_data = json.loads(
            (root / "tests" / "fixtures" / "cases" / "Robert.json").read_text(
                encoding="utf-8"
            )
        )
        facts = case_data["facts"]

        class FixtureRuleRepository:
            def __init__(self):
                self.texts = {
                    "drca_part_i_sections_1_to_13a": (
                        root
                        / "docs"
                        / "reference"
                        / "examples"
                        / "drca"
                        / "drca_part_i_sections_1_to_13a.txt"
                    ).read_text(encoding="utf-8"),
                    "drca_part_ii_sections_14_to_33": (
                        root
                        / "docs"
                        / "reference"
                        / "examples"
                        / "drca"
                        / "drca_part_ii_sections_14_to_33.txt"
                    ).read_text(encoding="utf-8"),
                }

            def find_rule_text_by_rule_name(self, name):
                text = self.texts.get(name)
                if text is None:
                    return None
                return RuleFileEntity(file_id=1, rule_id=1, files=text.encode("utf-8"))

            def find_rule_by_rule_name(self, name):
                return None

            def find_rule_by_rule_name_with_latest_history(self, name):
                return None

        store = InMemorySessionStore()
        service = InferenceSessionService(store)
        rule_service = RuleService(FixtureRuleRepository())
        root_rule_text = rule_service.get_rule_text(rule_name)
        expanded_rule_text = rule_service._build_import_aware_rule_text(
            rule_name,
            root_rule_text,
        )
        triples = sorted(
            set(InferraToRdfCompiler.compile(expanded_rule_text, rule_name))
        )
        rule_service.get_rule_ontology_data = MagicMock(
            return_value={
                "rule_name": rule_name,
                "source": "compiled",
                "triple_count": len(triples),
                "source_hash": build_projection_source_hash(expanded_rule_text),
                "graph_uri": FusekiAdapter.rule_projection_graph_uri(rule_name),
                "triples": [
                    {"subject": subject, "predicate": predicate, "object": obj}
                    for subject, predicate, obj in triples
                ],
            }
        )
        app.dependency_overrides[_session_service] = lambda: service
        app.dependency_overrides[_rule_service] = lambda: rule_service

        seen_questions = []
        final_next_question = None
        final_feed_response = None
        try:
            with patch(
                "src.adapters.inbound.http.routes.inference.run_post_reasoning"
            ):
                with TestClient(app) as c:
                    created = c.post(
                        "/api/v1/inference/sessions",
                        json={
                            "rule_name": rule_name,
                            "target_node_name": target_name,
                        },
                    )
                    assert created.status_code == 200
                    session_id = created.json()["session_id"]

                    for _ in range(80):
                        next_question = c.get(
                            f"/api/v1/inference/next-question?session_id={session_id}"
                        )
                        assert next_question.status_code == 200
                        question_data = next_question.json()
                        final_next_question = question_data
                        assert (
                            question_data["question_flow_state"]
                            != "BLOCKED_INCONSISTENT_STATE"
                        )
                        if not question_data["questions"]:
                            break

                        question_item = question_data["questions"][0]
                        question = question_item["question_text"]
                        seen_questions.append(question)
                        assert question in facts, f"Robert fixture missing {question!r}"
                        answer_type = question_item["question_value_type"].upper()
                        if answer_type == "NUMBER":
                            answer_type = "INTEGER"

                        feed = c.post(
                            f"/api/v1/inference/feed-answer?session_id={session_id}",
                            json={
                                "question": question,
                                "answer": {
                                    "type": answer_type,
                                    "answer": facts[question],
                                },
                            },
                        )
                        assert feed.status_code == 200
                        feed_data = feed.json()
                        if feed_data["has_more_questions"] is False:
                            final_feed_response = feed_data
                            final_next_question = c.get(
                                f"/api/v1/inference/next-question?session_id={session_id}"
                            ).json()
                            break
                    else:
                        pytest.fail("Robert fixture replay did not converge")

                    artifact = c.get(
                        f"/api/v1/inference/ontology-artifact?session_id={session_id}&case_name=Robert.json"
                    )
        finally:
            app.dependency_overrides.clear()

        assert "interim impairment assessment required" not in seen_questions
        assert "degree of permanent impairment assessed" not in seen_questions
        assert "medical provider status" not in seen_questions
        assert final_next_question["questions"] == []
        assert final_next_question["has_more_questions"] is False
        assert final_next_question["convergence_state"] == "GOAL_REACHED"
        assert final_next_question["question_flow_state"] == "GOAL_REACHED"
        assert final_feed_response == {
            "has_more_questions": False,
            "goal_rule_name": target_name,
            "goal_rule_value": "True",
            "goal_rule_type": "boolean",
        }
        assert artifact.status_code == 200
        artifact_data = artifact.json()
        assert artifact_data["artifact_name"] == "drca_part_ii_full_ontology.ttl"
        assert artifact_data["case_name"] == "Robert.json"
        assert artifact_data["deterministic_outcome_ref"] is not None
        assert "ontology_advisory_no_rule_execution_override" in artifact_data["turtle"]
        assert target_name in artifact_data["turtle"]
        rdflib.Graph().parse(data=artifact_data["turtle"], format="turtle")

    def test_public_api_converges_current_employee_branch_and_exports_artifact(self):
        rdflib = pytest.importorskip("rdflib")
        from src.adapters.inbound.http.routes.inference import (
            _rule_service,
            _session_service,
        )
        from src.domain.rule_parser.rule_set_parser import RuleSetParser
        from src.domain.rule_parser.rule_set_reader import RuleSetReader
        from src.domain.rule_parser.rule_set_scanner import RuleSetScanner

        rule_name = "drca_part_ii_sections_14_to_33"
        target_name = "DRCA part II sections 14 to 33 convergence met"
        rule_text = f"""
INPUT incapacity status AS LIST
    ITEM current employee
    ITEM former employee
    ITEM reservist
INPUT current employee evidence AS BOOLEAN
INPUT former employee evidence AS BOOLEAN
INPUT reserve earnings component AS NUMBER

{target_name}
    AND incapacity gateway met
        AND incapacity evaluation virtual ONE
            OR current employee path
                AND incapacity status = "current employee"
                AND current employee evidence
            OR former employee path
                AND incapacity status = "former employee"
                AND former employee evidence
            OR reservist path
                AND incapacity status = "reservist"
                AND KNOWN reserve earnings component
"""
        reader = RuleSetReader()
        reader.create()
        reader.set_file_with_text(rule_text)
        parser = RuleSetParser()
        parser.create()
        parser.set_source_name(rule_name)
        scanner = RuleSetScanner(reader, parser)
        scanner.scan_rule_set()
        node_set = scanner.establish_node_set()
        node_dict = node_set.get_node_dictionary()
        preferred_order = [
            target_name,
            "incapacity gateway met",
            "incapacity evaluation virtual ONE",
            "current employee path",
            "former employee path",
            "reservist path",
            'incapacity status = "current employee"',
            'incapacity status = "former employee"',
            'incapacity status = "reservist"',
            "current employee evidence",
            "former employee evidence",
            "reserve earnings component",
        ]
        node_set.set_sorted_node_list(
            [node_dict[name] for name in preferred_order]
            + [
                node
                for node in node_set.get_sorted_node_list()
                if node.get_node_name() not in preferred_order
            ]
        )

        store = InMemorySessionStore()
        service = InferenceSessionService(store)
        session = service.create_session(rule_name, target_name, node_set)
        rule_service = MagicMock(spec=RuleService)
        rule_service.get_rule_ontology_data.return_value = {
            "rule_name": rule_name,
            "source_hash": "synthetic-robert-current-employee-hash",
            "graph_uri": f"http://inferra.ai/schema#projection/rule/{rule_name}",
            "triples": [
                {
                    "subject": f"http://inferra.ai/schema#rule/{rule_name}",
                    "predicate": "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
                    "object": "http://inferra.ai/schema#RuleSet",
                },
                {
                    "subject": f"http://inferra.ai/schema#rule/{rule_name}",
                    "predicate": "http://inferra.ai/schema#name",
                    "object": rule_name,
                },
            ],
        }
        app.dependency_overrides[_session_service] = lambda: service
        app.dependency_overrides[_rule_service] = lambda: rule_service

        seen_questions = []
        try:
            with patch(
                "src.adapters.inbound.http.routes.inference.run_post_reasoning"
            ):
                with TestClient(app) as c:
                    next_question = c.get(
                        f"/api/v1/inference/next-question?session_id={session.session_id}"
                    )
                    assert next_question.status_code == 200

                    for _ in range(4):
                        data = next_question.json()
                        if not data["questions"]:
                            break
                        question = data["questions"][0]["question_text"]
                        seen_questions.append(question)
                        assert question not in {
                            "former employee evidence",
                            "reserve earnings component",
                        }
                        answer = (
                            {"type": "LIST", "answer": "current employee"}
                            if question == "incapacity status"
                            else {"type": "BOOLEAN", "answer": True}
                        )
                        feed = c.post(
                            f"/api/v1/inference/feed-answer?session_id={session.session_id}",
                            json={"question": question, "answer": answer},
                        )
                        assert feed.status_code == 200
                        if feed.json()["has_more_questions"] is False:
                            break
                        next_question = c.get(
                            f"/api/v1/inference/next-question?session_id={session.session_id}"
                        )
                        assert next_question.status_code == 200

                    final_question = c.get(
                        f"/api/v1/inference/next-question?session_id={session.session_id}"
                    )
                    artifact = c.get(
                        f"/api/v1/inference/ontology-artifact?session_id={session.session_id}&case_name=Robert.json"
                    )
        finally:
            app.dependency_overrides.clear()

        assert seen_questions == ["incapacity status", "current employee evidence"]
        assert final_question.status_code == 200
        assert final_question.json()["questions"] == []
        assert final_question.json()["has_more_questions"] is False
        assert final_question.json()["convergence_state"] == "GOAL_REACHED"
        assert artifact.status_code == 200
        artifact_data = artifact.json()
        assert artifact_data["deterministic_outcome_ref"] is not None
        assert artifact_data["case_name"] == "Robert.json"
        assert "ontology_advisory_no_rule_execution_override" in artifact_data["turtle"]
        assert target_name in artifact_data["turtle"]
        rdflib.Graph().parse(data=artifact_data["turtle"], format="turtle")


# =============================================================================
# IdempotencyStore
# =============================================================================

class TestIdempotencyStore:
    def test_put_and_get(self):
        from src.adapters.inbound.http.routes.inference import IdempotencyStore, FeedAnswerResponse
        store = IdempotencyStore()
        resp = FeedAnswerResponse(has_more_questions=True)
        store.put("key1", resp)
        assert store.get("key1") is resp

    def test_get_missing_returns_none(self):
        from src.adapters.inbound.http.routes.inference import IdempotencyStore
        store = IdempotencyStore()
        assert store.get("nonexistent") is None

    def test_ttl_expiry(self):
        from src.adapters.inbound.http.routes.inference import IdempotencyStore, FeedAnswerResponse
        store = IdempotencyStore(ttl_seconds=0)
        resp = FeedAnswerResponse(has_more_questions=True)
        store.put("key1", resp)
        import time
        time.sleep(0.01)
        assert store.get("key1") is None

    def test_lru_eviction(self):
        from src.adapters.inbound.http.routes.inference import IdempotencyStore, FeedAnswerResponse
        store = IdempotencyStore(max_size=2)
        store.put("k1", FeedAnswerResponse(has_more_questions=True))
        store.put("k2", FeedAnswerResponse(has_more_questions=True))
        store.put("k3", FeedAnswerResponse(has_more_questions=True))
        assert store.get("k1") is None
        assert store.get("k3") is not None

    def test_put_existing_moves_to_end(self):
        from src.adapters.inbound.http.routes.inference import IdempotencyStore, FeedAnswerResponse
        store = IdempotencyStore(max_size=2)
        store.put("k1", FeedAnswerResponse(has_more_questions=True))
        store.put("k2", FeedAnswerResponse(has_more_questions=True))
        store.put("k1", FeedAnswerResponse(has_more_questions=False))
        store.put("k3", FeedAnswerResponse(has_more_questions=True))
        assert store.get("k1") is not None
        assert store.get("k2") is None

    def test_clear(self):
        from src.adapters.inbound.http.routes.inference import IdempotencyStore, FeedAnswerResponse
        store = IdempotencyStore()
        store.put("k1", FeedAnswerResponse(has_more_questions=True))
        store.clear()
        assert store.get("k1") is None


# =============================================================================
# POST /api/v1/inference/sessions/ml
# =============================================================================

class TestCreateMLSession:
    @patch("src.domain.inference.session_service.InferenceSessionService.create_session_from_rule")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_create_ml_session_success(self, mock_init, mock_create):
        mock_session = _make_mock_session()
        mock_create.return_value = mock_session
        with TestClient(app) as c:
            response = c.post(
                "/api/v1/inference/sessions/ml",
                json={"rule_name": "test_rule", "target_node_name": "test_goal"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "test-session-123"

    @patch("src.domain.inference.session_service.InferenceSessionService.create_session_from_rule")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_create_ml_session_rule_not_found(self, mock_init, mock_create):
        mock_create.side_effect = LookupError("Rule 'missing' was not found")
        with TestClient(app) as c:
            response = c.post(
                "/api/v1/inference/sessions/ml",
                json={"rule_name": "missing", "target_node_name": "goal"},
            )
        assert response.status_code == 404


# =============================================================================
# POST /api/v1/inference/feed-answer — additional branches
# =============================================================================

class TestFeedAnswerAdditionalBranches:
    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_feed_answer_unsupported_type(self, mock_init, mock_get):
        session = _make_mock_session()
        mock_get.return_value = session
        with TestClient(app) as c:
            response = c.post(
                "/api/v1/inference/feed-answer?session_id=test-session-123",
                json={
                    "question": "age",
                    "answer": {"type": "unsupported_type", "answer": "val"},
                },
            )
        assert response.status_code == 400

    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_feed_answer_no_active_question(self, mock_init, mock_get):
        session = _make_mock_session()
        session.assessment.get_node_to_be_asked.return_value = None
        mock_get.return_value = session
        with TestClient(app) as c:
            response = c.post(
                "/api/v1/inference/feed-answer?session_id=test-session-123",
                json={
                    "question": "age",
                    "answer": {"type": "boolean", "answer": True},
                },
            )
        assert response.status_code == 400

    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_feed_answer_iterate_no_aux_node(self, mock_init, mock_get):
        session = _make_mock_session()
        mock_iterate = MagicMock()
        mock_iterate.get_line_type.return_value = LineType.ITERATE
        mock_iterate.get_node_name.return_value = "iter_node"
        session.assessment.get_node_to_be_asked.return_value = mock_iterate
        session.assessment.get_aux_node_to_be_asked.return_value = None
        mock_get.return_value = session
        with TestClient(app) as c:
            response = c.post(
                "/api/v1/inference/feed-answer?session_id=test-session-123",
                json={
                    "question": "iter_node",
                    "answer": {"type": "boolean", "answer": True},
                },
            )
        assert response.status_code == 400

    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_feed_answer_iterate_with_aux_node(self, mock_init, mock_get):
        session = _make_mock_session()
        mock_iterate = MagicMock()
        mock_iterate.get_line_type.return_value = LineType.ITERATE
        mock_iterate.get_node_name.return_value = "iter_node"
        mock_aux = MagicMock()
        mock_aux.get_node_name.return_value = "1st  var  q"
        session.assessment.get_node_to_be_asked.return_value = mock_iterate
        session.assessment.get_aux_node_to_be_asked.return_value = mock_aux
        mock_get.return_value = session
        with TestClient(app) as c:
            response = c.post(
                "/api/v1/inference/feed-answer?session_id=test-session-123",
                json={
                    "question": "1st  var  q",
                    "answer": {"type": "boolean", "answer": True},
                },
            )
        assert response.status_code in (200, 400)

    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_feed_answer_idempotency_cache_hit(self, mock_init, mock_get):
        from src.adapters.inbound.http.routes.inference import _idempotency_store, FeedAnswerResponse
        session = _make_mock_session()
        mock_get.return_value = session
        cached = FeedAnswerResponse(has_more_questions=False)
        _idempotency_store.put("test-session-123:cache-key-1", cached)
        with TestClient(app) as c:
            response = c.post(
                "/api/v1/inference/feed-answer?session_id=test-session-123",
                headers={"Idempotency-Key": "cache-key-1"},
                json={
                    "question": "age",
                    "answer": {"type": "boolean", "answer": True},
                },
            )
        assert response.status_code == 200
        _idempotency_store.clear()


# =============================================================================
# POST /api/v1/inference/reset-answer
# =============================================================================

class TestResetAnswer:
    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_reset_answer_has_more(self, mock_init, mock_get):
        session = _make_mock_session()
        session.inference_engine.edit_answer = MagicMock()
        mock_get.return_value = session
        with TestClient(app) as c:
            response = c.post(
                "/api/v1/inference/reset-answer?session_id=test-session-123",
                json={"question": "age"},
            )
        assert response.status_code == 200

    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_reset_answer_session_not_found(self, mock_init, mock_get):
        mock_get.return_value = None
        with TestClient(app) as c:
            response = c.post(
                "/api/v1/inference/reset-answer?session_id=nonexistent",
                json={"question": "age"},
            )
        assert response.status_code == 404

    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_reset_answer_unknown_question_returns_400(self, mock_init, mock_get):
        session = _make_mock_session()
        session.inference_engine.edit_answer = MagicMock(side_effect=ValueError("Question 'age' has not been answered"))
        mock_get.return_value = session
        with TestClient(app) as c:
            response = c.post(
                "/api/v1/inference/reset-answer?session_id=test-session-123",
                json={"question": "age"},
            )
        assert response.status_code == 400

    def test_reset_answer_persists_mutated_session(self):
        from src.adapters.inbound.http.routes.inference import _session_service

        session = _make_mock_session()
        session.inference_engine.edit_answer = MagicMock()
        store = InMemorySessionStore()
        store.save(session)
        service = InferenceSessionService(store)
        app.dependency_overrides[_session_service] = lambda: service

        try:
            with TestClient(app) as c:
                response = c.post(
                    "/api/v1/inference/reset-answer?session_id=test-session-123",
                    json={"question": "age"},
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        assert service.get_session("test-session-123").version == 1


# =============================================================================
# POST /api/v1/inference/history
# =============================================================================

class TestUpdateHistory:
    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    @patch("src.adapters.inbound.http.routes.inference.RuleService")
    def test_update_history_success(self, mock_rule_cls, mock_init, mock_get):
        mock_rule_svc = MagicMock()
        mock_rule_cls.return_value = mock_rule_svc
        mock_rule_svc.save_session_history.return_value = None
        session = _make_mock_session()
        mock_get.return_value = session
        with TestClient(app) as c:
            response = c.post(
                "/api/v1/inference/history?session_id=test-session-123",
                json={"rule_name": "test_rule"},
            )
        assert response.status_code == 200

    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_update_history_session_not_found(self, mock_init, mock_get):
        mock_get.return_value = None
        with TestClient(app) as c:
            response = c.post(
                "/api/v1/inference/history?session_id=nonexistent",
                json={"rule_name": "test_rule"},
            )
        assert response.status_code == 404


# =============================================================================
# GET /api/v1/inference/next-question — with iterate progress
# =============================================================================

class TestGetNextQuestionWithIterateProgress:
    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_iterate_node_with_progress(self, mock_init, mock_get):
        from src.domain.nodes.iterate_line import IterateLine
        session = _make_mock_session()
        mock_iterate = MagicMock(spec=IterateLine)
        mock_iterate.get_line_type.return_value = LineType.ITERATE
        mock_iterate.get_progress.return_value = (1, 3)
        session.assessment.get_node_to_be_asked.return_value = mock_iterate
        mock_next = MagicMock()
        mock_next.get_node_name.return_value = "1st  var  q"
        session.inference_engine.get_next_question_with_goal_name.return_value = mock_next
        session.inference_engine.find_type_of_element_to_be_asked.return_value = {"1st  var  q": FactValueType.BOOLEAN}
        session.inference_engine.get_questions_from_node_to_be_asked.return_value = ["1st  var  q"]
        mock_get.return_value = session
        with TestClient(app) as c:
            response = c.get("/api/v1/inference/next-question?session_id=test-session-123")
        assert response.status_code == 200
        data = response.json()
        assert data.get("iterate_progress") is not None

    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_no_more_questions(self, mock_init, mock_get):
        session = _make_mock_session()
        session.inference_engine.get_next_question_with_goal_name.return_value = None
        mock_get.return_value = session
        with TestClient(app) as c:
            response = c.get("/api/v1/inference/next-question?session_id=test-session-123")
        assert response.status_code == 200
        data = response.json()
        assert data["has_more_questions"] is False
        assert data["questions"] == []
        assert data["question_flow_state"] == "GOAL_REACHED"

    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_no_askable_question_with_unresolved_goal_returns_blocked_state(self, mock_init, mock_get):
        session = _make_mock_session()
        unresolved_state = AssessmentState()
        session.inference_engine.get_assessment_state.return_value = unresolved_state
        session.inference_engine.get_next_question_with_goal_name.return_value = None
        session.assessment.get_node_to_be_asked.return_value = None
        mock_get.return_value = session

        with TestClient(app) as c:
            response = c.get("/api/v1/inference/next-question?session_id=test-session-123")

        assert response.status_code == 200
        data = response.json()
        assert data["questions"] == []
        assert data["has_more_questions"] is False
        assert data["convergence_state"] == "PENDING"
        assert data["question_flow_state"] == "BLOCKED_INCONSISTENT_STATE"
        assert data["blocked_reason"] == "NO_ASKABLE_QUESTION"

    def test_next_question_persists_selected_question_state(self):
        from src.adapters.inbound.http.routes.inference import _session_service

        session = _make_mock_session()
        session.inference_engine.get_next_question_with_goal_name.return_value = None
        store = InMemorySessionStore()
        store.save(session)
        service = InferenceSessionService(store)
        app.dependency_overrides[_session_service] = lambda: service

        try:
            with TestClient(app) as c:
                response = c.get("/api/v1/inference/next-question?session_id=test-session-123")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        assert service.get_session("test-session-123").version == 1


# =============================================================================
# Direct branch coverage for response-shaping helpers
# =============================================================================


@pytest.mark.asyncio
async def test_session_context_reuses_existing_context():
    from src.adapters.inbound.http.routes.inference import _session_context

    session = _make_mock_session()
    context = InferenceContext(
        session_id="ctx-session",
        rule_name="rule",
        target="goal",
        mandatory=[],
        fact_store=MagicMock(),
    )
    session.context = context

    assert _session_context(session) is context


def test_create_session_impl_passes_authenticated_owner_id():
    from src.adapters.inbound.http.routes.inference import _create_session_impl

    session = _make_mock_session()
    session.llm_configuration = {"product_id": "axiom", "status": "configured"}
    session_service = MagicMock()
    session_service.create_session_from_rule.return_value = session

    response = _create_session_impl(
        "rule",
        "goal",
        False,
        MagicMock(),
        session_service,
        owner_id="user-1",
        llm_configuration_snapshot={"product_id": "axiom", "status": "configured"},
    )

    assert response.session_id == session.session_id
    assert response.llm_configuration == {"product_id": "axiom", "status": "configured"}
    session_service.create_session_from_rule.assert_called_once()
    assert session_service.create_session_from_rule.call_args.kwargs["owner_id"] == "user-1"
    assert session_service.create_session_from_rule.call_args.kwargs["llm_configuration"] == {
        "product_id": "axiom",
        "status": "configured",
    }


def test_session_owner_mismatch_returns_403():
    from fastapi import HTTPException
    from starlette.requests import Request
    from src.adapters.inbound.http.routes.inference import _enforce_session_owner
    from src.domain.state.feature_flags import FeatureFlags

    session = _make_mock_session()
    session.owner_id = "owner-a"
    request = Request({"type": "http", "headers": [], "inferra_user_id": "owner-b"})

    with patch("src.adapters.inbound.http.routes.inference.get_feature_flags", return_value=FeatureFlags(auth_enabled=True)):
        with pytest.raises(HTTPException) as exc:
            _enforce_session_owner(session, request)

    assert exc.value.status_code == 403
    assert exc.value.detail["error_code"] == "SESSION_OWNER_MISMATCH"


@pytest.mark.asyncio
async def test_reset_answer_returns_has_more_when_goal_not_complete():
    from src.adapters.inbound.http.routes.inference import reset_answer
    from src.adapters.inbound.http.schemas.inference import ResetAnswerRequest

    session = _make_mock_session()
    state = MagicMock()
    state.get_working_memory.return_value = {}
    state.all_mandatory_node_determined.return_value = False
    session.inference_engine.get_assessment_state.return_value = state

    response = await reset_answer(
        ResetAnswerRequest(question="age"),
        session_id=session.session_id,
        session=session,
    )

    assert response.has_more_questions is True
    session.inference_engine.edit_answer.assert_called_once_with("age")


@pytest.mark.asyncio
async def test_summary_formats_fact_sources_missing_summary_items_and_list_values():
    from src.adapters.inbound.http.routes.inference import get_summary

    session = _make_mock_session()
    session.feature_flags = FeatureFlags(enriched_api=True)
    session.context = InferenceContext(
        session_id=session.session_id,
        rule_name=session.rule_name,
        target=session.target_node_name,
        mandatory=[],
        fact_store=MagicMock(),
        reasoning_mode="ABDUCTION",
        confidence=0.7,
        induction_job_id="job-1",
    )
    state = MagicMock()
    state.get_working_memory.return_value = {
        "learned": FactValue("L", FactValueType.STRING),
        "hypothetical": FactValue("H", FactValueType.STRING),
        "semantic": FactValue("S", FactValueType.STRING),
        "list_fact": FactValue(
            [
                FactValue("one", FactValueType.STRING),
                FactValue("two", FactValueType.STRING),
            ]
        ),
    }
    state.get_summary_list.return_value = ["learned", "missing"]
    state.get_fact_store.return_value = _FakeFactStore(
        {
            "learned": {FactSource.LEARNED},
            "hypothetical": {FactSource.HYPOTHETICAL},
            "semantic": {FactSource.SEMANTIC},
            "list_fact": set(),
        }
    )
    state.all_mandatory_node_determined.return_value = False
    session.inference_engine.get_assessment_state.return_value = state

    response = await get_summary(
        session_id=session.session_id,
        offset=0,
        limit=0,
        session=session,
    )

    by_name = {item.node_text: item for item in response.summary}
    assert by_name["learned"].fact_source == FactSource.LEARNED.value
    assert by_name["hypothetical"].fact_source == FactSource.HYPOTHETICAL.value
    assert by_name["semantic"].fact_source == FactSource.SEMANTIC.value
    assert by_name["list_fact"].node_value == '["one", "two"]'
    assert "missing" not in by_name
    assert response.reasoning_mode == "ABDUCTION"
    assert response.origin_job_id == "job-1"


@pytest.mark.asyncio
async def test_summary_continues_when_fact_source_lookup_fails():
    from src.adapters.inbound.http.routes.inference import get_summary

    session = _make_mock_session()
    state = MagicMock()
    state.get_working_memory.return_value = {
        "x": FactValue("value", FactValueType.STRING),
    }
    state.get_summary_list.return_value = ["x"]
    state.get_fact_store.return_value = _FakeFactStore({"x": RuntimeError("layer down")})
    state.all_mandatory_node_determined.return_value = False
    session.inference_engine.get_assessment_state.return_value = state

    response = await get_summary(
        session_id=session.session_id,
        offset=0,
        limit=0,
        session=session,
    )

    assert response.summary[0].node_text == "x"
    assert response.summary[0].fact_source is None


@pytest.mark.asyncio
async def test_trace_runtime_error_becomes_503():
    from fastapi import HTTPException
    from src.adapters.inbound.http.routes.inference import get_trace

    session = _make_mock_session()
    session.feature_flags = FeatureFlags(prov_o_trace=True)
    session.context = InferenceContext(
        session_id=session.session_id,
        rule_name="rule",
        target="goal",
        mandatory=[],
        fact_store=MagicMock(),
    )

    with patch("src.adapters.inbound.http.routes.inference.ProvOTraceGenerator") as generator_cls:
        generator_cls.return_value.generate.side_effect = RuntimeError("trace disabled")
        with pytest.raises(HTTPException) as exc:
            await get_trace(
                session_id=session.session_id,
                trace_format="turtle",
                session=session,
            )

    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_stalled_next_question_invokes_session_orchestration():
    from src.adapters.inbound.http.routes.inference import get_next_question

    session = _make_mock_session()
    session.feature_flags = FeatureFlags(
        hybrid_orchestrator=True,
        reasoning_router=False,
    )
    unresolved_state = AssessmentState()
    session.inference_engine.get_assessment_state.return_value = unresolved_state
    session.inference_engine.get_next_question_with_goal_name.return_value = None
    session.assessment.get_node_to_be_asked.return_value = None
    runtime = MagicMock()
    runtime.evaluate_stalled_session = AsyncMock(
        return_value=ConvergenceResult(
            converged=False,
            reason="ITERATION_CAP",
            iteration=10,
            working_memory_hash="hash",
            ontology_delta=0,
            session_id=session.session_id,
        )
    )

    with patch(
        "src.adapters.inbound.http.routes.inference.get_inference_orchestration_service",
        return_value=runtime,
    ):
        response = await get_next_question(
            session_id=session.session_id,
            session=session,
            session_service=MagicMock(),
        )

    runtime.evaluate_stalled_session.assert_awaited_once_with(session)
    assert response.questions == []
    assert response.convergence_state == "ITERATION_CAP"


@pytest.mark.asyncio
async def test_terminal_goal_skips_alternate_reasoning_orchestration():
    from src.adapters.inbound.http.routes.inference import get_next_question

    session = _make_mock_session()
    session.feature_flags = FeatureFlags(
        hybrid_orchestrator=True,
        reasoning_router=True,
        abduction_enabled=True,
    )
    session.inference_engine.get_next_question_with_goal_name.return_value = None
    runtime = MagicMock()
    runtime.evaluate_stalled_session = AsyncMock()

    with patch(
        "src.adapters.inbound.http.routes.inference.get_inference_orchestration_service",
        return_value=runtime,
    ):
        response = await get_next_question(
            session_id=session.session_id,
            session=session,
            session_service=MagicMock(),
        )

    runtime.evaluate_stalled_session.assert_not_awaited()
    assert response.convergence_state == "GOAL_REACHED"


@pytest.mark.asyncio
async def test_update_history_lookup_error_becomes_404():
    from fastapi import HTTPException
    from src.adapters.inbound.http.routes.inference import update_history
    from src.adapters.inbound.http.schemas.inference import UpdateHistoryRequest

    session = _make_mock_session()
    rule_service = MagicMock()
    rule_service.save_session_history.side_effect = LookupError

    with pytest.raises(HTTPException) as exc:
        await update_history(
            UpdateHistoryRequest(rule_name="missing"),
            session_id=session.session_id,
            session=session,
            rule_service=rule_service,
        )

    assert exc.value.status_code == 404

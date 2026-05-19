"""
Integration tests for Phase 1 — §5 Scopes.

Covers the four integration scopes specified in the Phase 1 Implementation Plan §5:
1. FactStorePort → API  (layered memory flows through API responses)
2. Iterate progress → JSON  (iterate progress exposed in /next-question)
3. Validation gate → persistence  (RuleValidationService integrated with rule CRUD)
4. Correlation-ID tracing  (end-to-end request carries correlation ID)
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.domain.fact_values import FactValue, FactValueType
from src.domain.inference.assessment_state import AssessmentState
from src.domain.inference.session import InferenceSession
from src.domain.state.fact_source import FactSource
from src.main import app
from src.services.rule_validation_service import RuleValidationService


# =============================================================================
# 1. FactStorePort → API Integration
#    Layered memory must flow through API responses correctly.
# =============================================================================

class TestFactStoreToApiIntegration:
    """Integration: LayeredFactStore facts are correctly reflected in API responses."""

    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_asserted_fact_appears_in_summary(self, mock_init, mock_get):
        """An ASSERTED fact set via AssessmentState appears in /summary with fact_source."""
        assessment_state = AssessmentState()
        assessment_state.set_fact("age", FactValue(25, FactValueType.INTEGER), source=FactSource.ASSERTED)

        mock_ie = MagicMock()
        mock_ie.get_assessment_state.return_value = assessment_state
        mock_assessment = MagicMock()
        mock_goal = MagicMock()
        mock_goal.get_node_name.return_value = "goal"
        mock_assessment.get_goal_node.return_value = mock_goal
        mock_get.return_value = InferenceSession(
            session_id="s1", rule_name="r", target_node_name="goal",
            inference_engine=mock_ie, assessment=mock_assessment,
        )

        with TestClient(app) as c:
            resp = c.get("/api/v1/inference/summary?session_id=s1")

        assert resp.status_code == 200
        data = resp.json()
        age_items = [s for s in data["summary"] if s["node_text"] == "age"]
        assert len(age_items) == 1
        assert age_items[0]["node_value"] == "25"
        assert age_items[0]["fact_source"] == "ASSERTED"

    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_inferred_and_asserted_precedence(self, mock_init, mock_get):
        """When the same key is in both INFERRED and ASSERTED, ASSERTED wins in unified view."""
        assessment_state = AssessmentState()
        assessment_state.set_fact("score", FactValue(99, FactValueType.INTEGER), source=FactSource.INFERRED)
        assessment_state.set_fact("score", FactValue(100, FactValueType.INTEGER), source=FactSource.ASSERTED)

        mock_ie = MagicMock()
        mock_ie.get_assessment_state.return_value = assessment_state
        mock_assessment = MagicMock()
        mock_goal = MagicMock()
        mock_goal.get_node_name.return_value = "goal"
        mock_assessment.get_goal_node.return_value = mock_goal
        mock_get.return_value = InferenceSession(
            session_id="s2", rule_name="r", target_node_name="goal",
            inference_engine=mock_ie, assessment=mock_assessment,
        )

        with TestClient(app) as c:
            resp = c.get("/api/v1/inference/summary?session_id=s2")

        assert resp.status_code == 200
        data = resp.json()
        score_items = [s for s in data["summary"] if s["node_text"] == "score"]
        assert len(score_items) == 1
        # ASSERTED value (100) wins over INFERRED (99)
        assert score_items[0]["node_value"] == "100"
        assert score_items[0]["fact_source"] == "ASSERTED"

    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_invalidate_layer_removes_from_summary(self, mock_init, mock_get):
        """After invalidating the INFERRED layer, inferred facts disappear from summary."""
        assessment_state = AssessmentState()
        assessment_state.set_fact("x", FactValue(True, FactValueType.BOOLEAN), source=FactSource.INFERRED)
        assessment_state.set_fact("y", FactValue(42, FactValueType.INTEGER), source=FactSource.ASSERTED)

        # Invalidate INFERRED layer
        assessment_state.invalidate_layer(FactSource.INFERRED)

        mock_ie = MagicMock()
        mock_ie.get_assessment_state.return_value = assessment_state
        mock_assessment = MagicMock()
        mock_goal = MagicMock()
        mock_goal.get_node_name.return_value = "goal"
        mock_assessment.get_goal_node.return_value = mock_goal
        mock_get.return_value = InferenceSession(
            session_id="s3", rule_name="r", target_node_name="goal",
            inference_engine=mock_ie, assessment=mock_assessment,
        )

        with TestClient(app) as c:
            resp = c.get("/api/v1/inference/summary?session_id=s3")

        assert resp.status_code == 200
        data = resp.json()
        node_names = [s["node_text"] for s in data["summary"]]
        assert "x" not in node_names  # invalidated
        assert "y" in node_names      # still present


# =============================================================================
# 2. Iterate Progress → JSON Integration
#    Iterate progress must be exposed correctly in /next-question.
# =============================================================================

class TestIterateProgressIntegration:
    """Integration: IterateContext progress flows through /next-question."""

    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_iterate_progress_in_next_question_response(self, mock_init, mock_get):
        """When active node is IterateLine, iterate_progress is in the response."""
        from src.domain.nodes.iterate_line import IterateLine
        from src.domain.nodes.line_type import LineType

        mock_iterate = MagicMock(spec=IterateLine)
        mock_iterate.get_line_type.return_value = LineType.ITERATE
        mock_iterate.get_progress.return_value = (3, 5)
        mock_iterate.get_number_of_target.return_value = "ALL"
        mock_iterate.get_given_list_name.return_value = "services"

        mock_next_node = MagicMock()
        mock_next_node.get_line_type.return_value = LineType.COMPARISON

        mock_ie = MagicMock()
        mock_ie.get_next_question_with_goal_name.return_value = mock_next_node
        # Return False for all_mandatory_node_determined so has_more is True
        # Use a real AssessmentState (empty mandatory list = all_mandatory_node_determined = True)
        # so we need to add items to mandatory list first
        mock_assessment_state = MagicMock()
        mock_assessment_state.get_working_memory.return_value = {}
        mock_assessment_state.all_mandatory_node_determined.return_value = False
        mock_assessment_state.get_summary_list.return_value = []
        mock_ie.get_assessment_state.return_value = mock_assessment_state
        mock_ie.find_type_of_element_to_be_asked.return_value = {"q": FactValueType.BOOLEAN}
        mock_ie.get_questions_from_node_to_be_asked.return_value = ["q"]

        mock_assessment = MagicMock()
        mock_assessment.get_node_to_be_asked.return_value = mock_iterate
        mock_assessment.get_aux_node_to_be_asked.return_value = mock_next_node
        mock_assessment.get_goal_node.return_value = MagicMock()
        mock_goal = MagicMock()
        mock_goal.get_node_name.return_value = "goal"
        mock_assessment.get_goal_node.return_value = mock_goal

        mock_get.return_value = InferenceSession(
            session_id="s4", rule_name="r", target_node_name="goal",
            inference_engine=mock_ie, assessment=mock_assessment,
        )

        with TestClient(app) as c:
            resp = c.get("/api/v1/inference/next-question?session_id=s4")

        assert resp.status_code == 200
        data = resp.json()
        assert data["iterate_progress"] is not None
        assert data["iterate_progress"]["answered"] == 3
        assert data["iterate_progress"]["total"] == 5


# =============================================================================
# 3. Validation Gate → Persistence Integration
#    RuleValidationService must be integrated into the rule CRUD flow.
# =============================================================================

class TestValidationGateIntegration:
    """Integration: RuleValidationService validates before rule persistence."""

    def test_invalid_rule_returns_errors(self):
        """An invalid rule (duplicate INPUT) returns valid=False with structured errors."""
        svc = RuleValidationService()
        result = svc.validate(
            rule_text="INPUT x AS NUMBER\nINPUT x AS NUMBER\n",
            rule_name="bad_rule",
        )
        assert result.valid is False
        assert len(result.errors) > 0
        assert any("duplicate" in e.code.lower() or "DUPLICATE" in e.code for e in result.errors)

    def test_valid_rule_passes_validation(self):
        """A valid rule returns valid=True with no errors."""
        svc = RuleValidationService()
        result = svc.validate(
            rule_text="INPUT age AS NUMBER\nage > 18\n",
            rule_name="adult_check",
        )
        assert result.valid is True
        assert len(result.errors) == 0

    def test_validation_cache_hit(self):
        """Same rule text returns cached result on second call."""
        svc = RuleValidationService()
        text = "INPUT x AS NUMBER\nx > 0\n"
        r1 = svc.validate(text, "rule_a")
        r2 = svc.validate(text, "rule_a")
        assert r1.valid == r2.valid
        assert r1.errors == r2.errors

    def test_validation_endpoint_blocks_invalid_rule(self):
        """POST /api/v1/rules/validate returns valid=False for cyclic rules."""
        with TestClient(app) as c:
            resp = c.post(
                "/api/v1/rules/validate",
                json={
                    "rule_text": "INPUT a AS NUMBER\nINPUT b AS NUMBER\na IS CALC b + 1\nb IS CALC a + 1\n",
                    "rule_name": "cyclic",
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False


# =============================================================================
# 4. Correlation-ID Tracing Integration
#    End-to-end request carries correlation ID through all layers.
# =============================================================================

class TestCorrelationIdTracingIntegration:
    """Integration: Correlation-ID flows from request header to response header."""

    def test_correlation_id_propagated_in_response(self):
        """X-Correlation-ID in request appears in response headers."""
        with TestClient(app) as c:
            resp = c.get("/health", headers={"X-Correlation-ID": "test-correlation-123"})

        assert resp.status_code == 200
        assert resp.headers.get("X-Correlation-ID") == "test-correlation-123"

    def test_correlation_id_generated_when_missing(self):
        """A new X-Correlation-ID is generated when not provided by client."""
        with TestClient(app) as c:
            resp = c.get("/health")

        assert resp.status_code == 200
        correlation_id = resp.headers.get("X-Correlation-ID")
        assert correlation_id is not None
        # Should be a valid UUID format
        import uuid
        uuid.UUID(correlation_id)  # Will raise if invalid

    def test_different_requests_get_different_ids(self):
        """Different requests without X-Correlation-ID get different IDs."""
        with TestClient(app) as c:
            resp1 = c.get("/health")
            resp2 = c.get("/health")

        id1 = resp1.headers.get("X-Correlation-ID")
        id2 = resp2.headers.get("X-Correlation-ID")
        assert id1 != id2

    def test_validation_endpoint_carries_correlation_id(self):
        """Correlation-ID is preserved even on validation error paths."""
        with TestClient(app) as c:
            resp = c.post(
                "/api/v1/rules/validate",
                json={"rule_text": "", "rule_name": "empty"},
                headers={"X-Correlation-ID": "val-trace-456"},
            )

        assert resp.headers.get("X-Correlation-ID") == "val-trace-456"

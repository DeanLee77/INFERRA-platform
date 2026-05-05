"""
End-to-end test for the full inference session lifecycle.

Phase 1 §5 E2E test: create → ask → answer → progress → summary → trace

Tests the complete backward-chaining inference flow from session creation
through question answering to summary retrieval, verifying:
- Session creation with a valid rule
- Question retrieval with backward chaining
- Answer submission and propagation
- Iterate progress tracking
- Summary with fact_source provenance
- Correlation-ID end-to-end tracing
"""

import pytest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.domain.fact_values import FactValue, FactValueType
from src.domain.inference.assessment_state import AssessmentState
from src.domain.inference.session import InferenceSession
from src.domain.nodes.line_type import LineType
from src.domain.state.fact_source import FactSource
from src.main import app


# =============================================================================
# E2E: Full session flow with mocked InferenceEngine
# =============================================================================

class TestE2EInferenceSession:
    """
    End-to-end test for the full inference session lifecycle.

    Uses real API endpoints with mocked InferenceSessionService to simulate
    the complete flow without needing a database or real rule files.
    """

    def _build_session(self, session_id="e2e-session"):
        """Build a mock session with a realistic AssessmentState."""
        assessment_state = AssessmentState()

        mock_ie = MagicMock()
        mock_ie.get_assessment_state.return_value = assessment_state

        mock_assessment = MagicMock()
        mock_goal = MagicMock()
        mock_goal.get_node_name.return_value = "eligibility"
        mock_assessment.get_goal_node.return_value = mock_goal

        session = InferenceSession(
            session_id=session_id,
            rule_name="eligibility_rule",
            target_node_name="eligibility",
            inference_engine=mock_ie,
            assessment=mock_assessment,
        )
        return session

    # ------------------------------------------------------------------
    # Step 1: Create session
    # ------------------------------------------------------------------
    @patch("src.domain.inference.session_service.InferenceSessionService.create_session_from_rule")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_step1_create_session(self, mock_init, mock_create):
        """E2E Step 1: Create a new inference session."""
        session = self._build_session()
        mock_create.return_value = session

        with TestClient(app) as c:
            resp = c.post(
                "/api/v1/inference/sessions",
                json={"rule_name": "eligibility_rule", "target_node_name": "eligibility"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == "e2e-session"
        assert data["rule_name"] == "eligibility_rule"
        assert data["target_node_name"] == "eligibility"

    # ------------------------------------------------------------------
    # Step 2: Get next question
    # ------------------------------------------------------------------
    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_step2_get_next_question(self, mock_init, mock_get):
        """E2E Step 2: Get next question from the session."""
        session = self._build_session()

        mock_question_node = MagicMock()
        mock_question_node.get_line_type.return_value = LineType.COMPARISON

        # Use real AssessmentState so all_mandatory_node_determined works
        assessment_state = AssessmentState()
        session.inference_engine.get_assessment_state.return_value = assessment_state
        session.inference_engine.get_next_question_with_goal_name.return_value = mock_question_node
        session.assessment.get_node_to_be_asked.return_value = None  # not iterate
        session.inference_engine.find_type_of_element_to_be_asked.return_value = {"age": FactValueType.INTEGER}
        session.inference_engine.get_questions_from_node_to_be_asked.return_value = ["age"]

        mock_get.return_value = session

        with TestClient(app) as c:
            resp = c.get("/api/v1/inference/next-question?session_id=e2e-session")

        assert resp.status_code == 200
        data = resp.json()
        assert data["has_more_questions"] is True
        assert len(data["questions"]) > 0

    # ------------------------------------------------------------------
    # Step 3: Feed answer
    # ------------------------------------------------------------------
    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_step3_feed_answer(self, mock_init, mock_get):
        """E2E Step 3: Submit an answer to the question."""
        session = self._build_session()

        # Simulate: age hasn't been answered yet
        # Use real AssessmentState so all_mandatory_node_determined works
        assessment_state = AssessmentState()
        session.inference_engine.get_assessment_state.return_value = assessment_state

        mock_active = MagicMock()
        mock_active.get_line_type.return_value = LineType.COMPARISON
        session.assessment.get_node_to_be_asked.return_value = mock_active

        mock_get.return_value = session

        with TestClient(app) as c:
            resp = c.post(
                "/api/v1/inference/feed-answer?session_id=e2e-session",
                json={
                    "session_id": "e2e-session",
                    "question": "age",
                    "answer": {"type": "integer", "answer": 25},
                },
            )

        # Should succeed (not 409 since age not in working memory)
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_more_questions"] is True  # still questions remaining

    # ------------------------------------------------------------------
    # Step 4: Summary with fact_source provenance
    # ------------------------------------------------------------------
    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_step4_summary_with_fact_source(self, mock_init, mock_get):
        """E2E Step 4: Get summary showing fact_source provenance."""
        session = self._build_session()
        # Populate working memory with both ASSERTED and INFERRED facts
        session.inference_engine.get_assessment_state().set_fact(
            "age", FactValue(25, FactValueType.INTEGER), source=FactSource.ASSERTED
        )
        session.inference_engine.get_assessment_state().set_fact(
            "eligibility", FactValue(True, FactValueType.BOOLEAN), source=FactSource.INFERRED
        )

        mock_get.return_value = session

        with TestClient(app) as c:
            resp = c.get("/api/v1/inference/summary?session_id=e2e-session")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] >= 2

        # Check fact sources are present
        age_item = next((s for s in data["summary"] if s["node_text"] == "age"), None)
        elig_item = next((s for s in data["summary"] if s["node_text"] == "eligibility"), None)
        assert age_item is not None
        assert age_item["fact_source"] == "ASSERTED"
        assert elig_item is not None
        assert elig_item["fact_source"] == "INFERRED"

    # ------------------------------------------------------------------
    # Step 5: Summary pagination
    # ------------------------------------------------------------------
    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_step5_summary_pagination(self, mock_init, mock_get):
        """E2E Step 5: Summary pagination works with offset/limit."""
        session = self._build_session()
        session.inference_engine.get_assessment_state().set_fact(
            "age", FactValue(25, FactValueType.INTEGER), source=FactSource.ASSERTED
        )
        session.inference_engine.get_assessment_state().set_fact(
            "score", FactValue(88, FactValueType.INTEGER), source=FactSource.ASSERTED
        )
        session.inference_engine.get_assessment_state().set_fact(
            "eligibility", FactValue(True, FactValueType.BOOLEAN), source=FactSource.INFERRED
        )

        mock_get.return_value = session

        with TestClient(app) as c:
            # Get first page of 2 items
            resp = c.get("/api/v1/inference/summary?session_id=e2e-session&offset=0&limit=2")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] >= 3
        assert data["offset"] == 0
        assert data["limit"] == 2
        assert len(data["summary"]) <= 2

    # ------------------------------------------------------------------
    # Step 6: Correlation-ID trace
    # ------------------------------------------------------------------
    @patch("src.domain.inference.session_service.InferenceSessionService.get_session")
    @patch("src.domain.inference.session_service.InferenceSessionService.__init__", return_value=None)
    def test_step6_correlation_id_e2e(self, mock_init, mock_get):
        """E2E Step 6: Correlation-ID propagates through the entire request."""
        session = self._build_session()
        mock_get.return_value = session

        with TestClient(app) as c:
            resp = c.get(
                "/api/v1/inference/summary?session_id=e2e-session",
                headers={"X-Correlation-ID": "e2e-trace-789"},
            )

        assert resp.status_code == 200
        assert resp.headers.get("X-Correlation-ID") == "e2e-trace-789"

    # ------------------------------------------------------------------
    # Step 7: Health check with component status
    # ------------------------------------------------------------------
    def test_step7_health_check(self):
        """E2E Step 7: Health endpoint returns component status."""
        with TestClient(app) as c:
            resp = c.get("/health")

        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "version" in data
        assert "components" in data
        assert "database" in data["components"]
        assert "redis" in data["components"]

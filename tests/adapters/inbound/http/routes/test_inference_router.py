"""
Integration tests for the inference router.

Covers session lifecycle, question/answer flow, summary pagination,
idempotency, and error handling using FastAPI TestClient with
dependency overrides.
"""

import pytest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.main import app
from src.adapters.outbound.session.in_memory_session_store import InMemorySessionStore
from src.domain.exceptions import ConcurrentModificationError
from src.domain.fact_values import FactValue, FactValueType
from src.domain.session import InferenceContext
from src.domain.state.fact_source import FactSource
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


# =============================================================================
# POST /api/v1/inference/sessions
# =============================================================================

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
    def test_trace_session_not_found(self, mock_init, mock_get):
        mock_get.return_value = None

        with TestClient(app) as c:
            response = c.get("/api/v1/inference/trace?session_id=nonexistent")

        assert response.status_code == 404


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
    session_service = MagicMock()
    session_service.create_session_from_rule.return_value = session

    response = _create_session_impl(
        "rule",
        "goal",
        False,
        MagicMock(),
        session_service,
        owner_id="user-1",
    )

    assert response.session_id == session.session_id
    session_service.create_session_from_rule.assert_called_once()
    assert session_service.create_session_from_rule.call_args.kwargs["owner_id"] == "user-1"


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

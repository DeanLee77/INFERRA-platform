"""
Tests for InMemorySessionStore.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from src.adapters.outbound.session.in_memory_session_store import InMemorySessionStore
from src.domain.exceptions import ConcurrentModificationError
from src.domain.inference.session import InferenceSession


@pytest.fixture
def session_store():
    """Create a fresh session store for each test."""
    return InMemorySessionStore()


@pytest.fixture
def mock_inference_engine():
    """Create a mock inference engine."""
    engine = MagicMock()
    engine.get_node_set().get_node_set_name.return_value = "test_rule"
    return engine


@pytest.fixture
def mock_assessment():
    """Create a mock assessment."""
    assessment = MagicMock()
    assessment.get_goal_node().get_node_name.return_value = "test_goal"
    return assessment


@pytest.fixture
def sample_session(mock_inference_engine, mock_assessment):
    """Create a sample inference session."""
    return InferenceSession(
        session_id="test-session-123",
        rule_name="test_rule",
        target_node_name="test_goal",
        inference_engine=mock_inference_engine,
        assessment=mock_assessment,
    )


class TestInMemorySessionStore:
    """Tests for InMemorySessionStore."""
    
    def test_save_and_get_session(self, session_store, sample_session):
        """Test saving and retrieving a session."""
        session_store.save(sample_session)
        
        retrieved = session_store.get("test-session-123")
        
        assert retrieved is not None
        assert retrieved.session_id == "test-session-123"
        assert retrieved.rule_name == "test_rule"
        assert retrieved.target_node_name == "test_goal"
    
    def test_get_nonexistent_session(self, session_store):
        """Test retrieving a session that doesn't exist."""
        result = session_store.get("nonexistent-id")
        
        assert result is None
    
    def test_delete_session(self, session_store, sample_session):
        """Test deleting a session."""
        session_store.save(sample_session)
        
        deleted = session_store.delete("test-session-123")
        
        assert deleted is True
        assert session_store.get("test-session-123") is None
    
    def test_delete_nonexistent_session(self, session_store):
        """Test deleting a session that doesn't exist."""
        deleted = session_store.delete("nonexistent-id")
        
        assert deleted is False
    
    def test_exists(self, session_store, sample_session):
        """Test checking if a session exists."""
        assert session_store.exists("test-session-123") is False
        
        session_store.save(sample_session)
        
        assert session_store.exists("test-session-123") is True
    
    def test_list_sessions(self, session_store, sample_session, mock_inference_engine, mock_assessment):
        """Test listing all sessions."""
        assert session_store.list_sessions() == []
        
        session_store.save(sample_session)
        
        another_session = InferenceSession(
            session_id="another-session-456",
            rule_name="another_rule",
            target_node_name="another_goal",
            inference_engine=mock_inference_engine,
            assessment=mock_assessment,
        )
        session_store.save(another_session)
        
        sessions = session_store.list_sessions()
        
        assert len(sessions) == 2
        assert "test-session-123" in sessions
        assert "another-session-456" in sessions
    
    def test_clear_expired(self, session_store, sample_session, mock_inference_engine, mock_assessment):
        """Test clearing expired sessions."""
        # Save a fresh session
        session_store.save(sample_session)
        
        # Create an expired session
        expired_session = InferenceSession(
            session_id="expired-session",
            rule_name="expired_rule",
            target_node_name="expired_goal",
            inference_engine=mock_inference_engine,
            assessment=mock_assessment,
        )
        # Manually set last_accessed to the past
        expired_session.last_accessed = datetime.utcnow() - timedelta(hours=2)
        session_store.save(expired_session)
        
        # Clear sessions older than 1 hour
        cleared = session_store.clear_expired(max_age_seconds=3600)
        
        assert cleared == 1
        assert session_store.exists("test-session-123") is True
        assert session_store.exists("expired-session") is False
    
    def test_clear_all(self, session_store, sample_session, mock_inference_engine, mock_assessment):
        """Test clearing all sessions."""
        session_store.save(sample_session)
        
        another_session = InferenceSession(
            session_id="another-session",
            rule_name="another_rule",
            target_node_name="another_goal",
            inference_engine=mock_inference_engine,
            assessment=mock_assessment,
        )
        session_store.save(another_session)
        
        session_store.clear_all()
        
        assert session_store.count() == 0
    
    def test_touch_updates_last_accessed(self, session_store, sample_session):
        """Test that get() updates last_accessed timestamp."""
        session_store.save(sample_session)
        
        # Wait a moment
        import time
        time.sleep(0.01)
        
        original_time = sample_session.last_accessed
        session_store.get("test-session-123")
        
        assert sample_session.last_accessed > original_time
    
    def test_count(self, session_store, sample_session, mock_inference_engine, mock_assessment):
        """Test counting sessions."""
        assert session_store.count() == 0
        
        session_store.save(sample_session)
        
        assert session_store.count() == 1
        
        another_session = InferenceSession(
            session_id="another-session",
            rule_name="another_rule",
            target_node_name="another_goal",
            inference_engine=mock_inference_engine,
            assessment=mock_assessment,
        )
        session_store.save(another_session)
        
        assert session_store.count() == 2

    def test_save_increments_version_on_update(self, session_store, sample_session):
        session_store.save(sample_session)
        assert sample_session.version == 0

        session_store.save(sample_session)
        assert sample_session.version == 1

    def test_stale_save_raises_concurrent_modification(
        self, session_store, sample_session, mock_inference_engine, mock_assessment
    ):
        session_store.save(sample_session)
        stale_copy = InferenceSession(
            session_id=sample_session.session_id,
            rule_name=sample_session.rule_name,
            target_node_name=sample_session.target_node_name,
            inference_engine=mock_inference_engine,
            assessment=mock_assessment,
            version=sample_session.version,
        )

        session_store.save(sample_session)

        with pytest.raises(ConcurrentModificationError):
            session_store.save(stale_copy)

"""
Tests for the InferenceSessionService.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

from src.domain.inference.session_service import InferenceSessionService
from src.domain.inference.session import InferenceSession


@pytest.fixture
def mock_session_store():
    """Create a mock session store."""
    return MagicMock()


@pytest.fixture
def inference_session_service(mock_session_store):
    """Create an InferenceSessionService instance."""
    return InferenceSessionService(mock_session_store)


class TestInferenceSessionService:
    """Tests for InferenceSessionService."""
    
    def test_generate_session_id(self, inference_session_service):
        """Test session ID generation."""
        with patch("uuid.uuid4") as mock_uuid:
            mock_uuid.return_value = "test-uuid-123"
            
            result = inference_session_service.generate_session_id()
            
            assert result == "test-uuid-123"
            mock_uuid.assert_called_once()
    
    def test_generate_session_id_unique(self, inference_session_service):
        """Test that session IDs are unique."""
        id1 = inference_session_service.generate_session_id()
        id2 = inference_session_service.generate_session_id()
        
        assert id1 != id2
        assert len(id1) == 36  # UUID format
    
    def test_get_session(self, inference_session_service, mock_session_store):
        """Test getting an existing session."""
        mock_session = InferenceSession(
            session_id="test-session-123",
            rule_name="test_rule",
            target_node_name="test_goal",
            inference_engine=MagicMock(),
            assessment=MagicMock(),
        )
        mock_session_store.get.return_value = mock_session
        
        result = inference_session_service.get_session("test-session-123")
        
        assert result == mock_session
        mock_session_store.get.assert_called_once_with("test-session-123")
    
    def test_get_nonexistent_session(self, inference_session_service, mock_session_store):
        """Test getting a non-existent session."""
        mock_session_store.get.return_value = None
        
        result = inference_session_service.get_session("nonexistent-session")
        
        assert result is None
        mock_session_store.get.assert_called_once_with("nonexistent-session")
    
    def test_delete_session(self, inference_session_service, mock_session_store):
        """Test deleting a session."""
        mock_session_store.delete.return_value = True
        
        result = inference_session_service.delete_session("test-session-123")
        
        assert result is True
        mock_session_store.delete.assert_called_once_with("test-session-123")
    
    def test_session_exists_true(self, inference_session_service, mock_session_store):
        """Test checking if a session exists."""
        mock_session_store.exists.return_value = True
        
        result = inference_session_service.session_exists("test-session-123")
        
        assert result is True
        mock_session_store.exists.assert_called_once_with("test-session-123")
    
    def test_session_exists_false(self, inference_session_service, mock_session_store):
        """Test checking if a non-existent session exists."""
        mock_session_store.exists.return_value = False
        
        result = inference_session_service.session_exists("nonexistent")
        
        assert result is False
    
    def test_clear_expired_sessions(self, inference_session_service, mock_session_store):
        """Test clearing expired sessions."""
        mock_session_store.clear_expired.return_value = 5
        
        result = inference_session_service.clear_expired_sessions(3600)
        
        assert result == 5
        mock_session_store.clear_expired.assert_called_once_with(3600)
    
    def test_create_session_success(self, inference_session_service, mock_session_store):
        """Test creating a new inference session."""
        mock_node_set = MagicMock()
        mock_node_set.get_node_dictionary.return_value = {"test_goal": MagicMock()}
        
        mock_inference_engine = MagicMock()
        mock_inference_engine.get_node_set.return_value = mock_node_set
        
        with patch("src.domain.inference.session_service.InferenceEngine") as mock_engine_class, \
             patch("src.domain.inference.session_service.Assessment") as mock_assessment_class:
            
            mock_engine_class.return_value = mock_inference_engine
            
            session = inference_session_service.create_session(
                rule_name="test_rule",
                target_node_name="test_goal",
                node_set=mock_node_set,
            )
            
            assert session.session_id is not None
            assert session.rule_name == "test_rule"
            assert session.target_node_name == "test_goal"
            
            mock_session_store.save.assert_called_once_with(session)
    
    def test_create_session_invalid_target(self, inference_session_service, mock_session_store):
        """Test creating a session with invalid target node."""
        mock_node_set = MagicMock()
        mock_node_set.get_node_dictionary.return_value = {}
        
        with pytest.raises(ValueError, match="Target node 'invalid_goal' does not exist"):
            inference_session_service.create_session(
                rule_name="test_rule",
                target_node_name="invalid_goal",
                node_set=mock_node_set,
            )
    
    def test_create_session_from_rule_success(self, inference_session_service, mock_session_store):
        """Test creating a session from a rule."""
        mock_node_set = MagicMock()
        mock_node_set.get_node_dictionary.return_value = {"test_goal": MagicMock()}
        
        mock_parser = MagicMock()
        mock_parser.get_node_set.return_value = mock_node_set
        
        mock_rule_service = MagicMock()
        mock_rule_service.build_rule_set_parser.return_value = mock_parser
        
        mock_inference_engine = MagicMock()
        mock_inference_engine.get_node_set.return_value = mock_node_set
        
        with patch("src.domain.inference.session_service.InferenceEngine") as mock_engine_class, \
             patch("src.domain.inference.session_service.Assessment"):
            
            mock_engine_class.return_value = mock_inference_engine
            
            session = inference_session_service.create_session_from_rule(
                rule_name="test_rule",
                target_node_name="test_goal",
                rule_service=mock_rule_service,
            )
            
            assert session.session_id is not None
            assert session.rule_name == "test_rule"
            assert session.target_node_name == "test_goal"
            
            mock_rule_service.build_rule_set_parser.assert_called_once()
    
    def test_create_session_from_rule_with_history(self, inference_session_service, mock_session_store):
        """Test creating an ML-enhanced session from a rule."""
        mock_node_set = MagicMock()
        mock_node_set.get_node_dictionary.return_value = {"test_goal": MagicMock()}
        
        mock_parser = MagicMock()
        mock_parser.get_node_set.return_value = mock_node_set
        
        mock_rule_service = MagicMock()
        mock_rule_service.build_rule_set_parser.return_value = mock_parser
        mock_rule_service.get_history_for_ml_inference.return_value = {"history": "data"}
        
        mock_inference_engine = MagicMock()
        mock_inference_engine.get_node_set.return_value = mock_node_set
        
        with patch("src.domain.inference.session_service.InferenceEngine") as mock_engine_class, \
             patch("src.domain.inference.session_service.Assessment"):
            
            mock_engine_class.return_value = mock_inference_engine
            
            session = inference_session_service.create_session_from_rule(
                rule_name="test_rule",
                target_node_name="test_goal",
                rule_service=mock_rule_service,
                use_history=True,
            )
            
            assert session.session_id is not None
            mock_rule_service.get_history_for_ml_inference.assert_called_once_with("test_rule")

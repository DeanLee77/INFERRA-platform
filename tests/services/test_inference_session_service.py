"""
Tests for the InferenceSessionService.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

from src.domain.inference.session_service import InferenceSessionService
from src.domain.inference.session import InferenceSession
from src.domain.inference.semantic_question_strategy import SemanticQuestionStrategy
from src.domain.state.feature_flags import FeatureFlags


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

    def test_create_session_applies_requested_ontology_profile(self, inference_session_service, mock_session_store):
        mock_node_set = MagicMock()
        mock_node_set.get_node_dictionary.return_value = {"test_goal": MagicMock()}

        mock_inference_engine = MagicMock()
        mock_inference_engine.get_node_set.return_value = mock_node_set

        with patch(
            "src.domain.inference.session_service.get_feature_flags",
            return_value=FeatureFlags(
                ontology_advisory_enabled=False,
                ontology_auto_answer=False,
                ontology_reasoning=False,
                ontology_question_strategy=False,
            ),
        ), patch("src.domain.inference.session_service.InferenceEngine") as mock_engine_class, \
             patch("src.domain.inference.session_service.Assessment"):
            mock_engine_class.return_value = mock_inference_engine

            session = inference_session_service.create_session(
                rule_name="test_rule",
                target_node_name="test_goal",
                node_set=mock_node_set,
                ontology_profile="reasoning",
                ontology_flags={"auto_answer_enabled": False},
            )

        session_flags = session.feature_flags
        assert session.ontology_profile == "custom"
        assert session.ontology_profile_source == "request"
        assert session_flags.ontology_advisory_enabled is True
        assert session_flags.ontology_auto_answer is False
        assert session_flags.ontology_reasoning is True
        assert session_flags.ontology_question_strategy is False
        assert session_flags.is_frozen() is True

    def test_create_session_stores_llm_configuration_snapshot(self, inference_session_service, mock_session_store):
        mock_node_set = MagicMock()
        mock_node_set.get_node_dictionary.return_value = {"test_goal": MagicMock()}

        mock_inference_engine = MagicMock()
        mock_inference_engine.get_node_set.return_value = mock_node_set

        snapshot = {"product_id": "axiom", "status": "configured"}

        with patch("src.domain.inference.session_service.InferenceEngine") as mock_engine_class, \
             patch("src.domain.inference.session_service.Assessment"):
            mock_engine_class.return_value = mock_inference_engine

            session = inference_session_service.create_session(
                rule_name="test_rule",
                target_node_name="test_goal",
                node_set=mock_node_set,
                llm_configuration=snapshot,
            )

        assert session.llm_configuration == snapshot
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

    @pytest.mark.parametrize(
        "key",
        ["use_hypergraph", "layered_memory", "strict_port_contracts"],
    )
    def test_create_session_rejects_unsupported_runtime_profile(
        self,
        inference_session_service,
        key,
    ):
        node_set = MagicMock()
        node_set.get_node_dictionary.return_value = {"test_goal": MagicMock()}

        with patch(
            "src.domain.inference.session_service.get_feature_flags",
            return_value=FeatureFlags(**{key: False}),
        ), pytest.raises(RuntimeError, match=rf"{key} must be true"):
            inference_session_service.create_session(
                rule_name="test_rule",
                target_node_name="test_goal",
                node_set=node_set,
            )
    
    def test_create_session_from_rule_success(self, inference_session_service, mock_session_store):
        """Test creating a session from a rule."""
        mock_node_set = MagicMock()
        mock_node_set.get_node_dictionary.return_value = {"test_goal": MagicMock()}
        
        mock_parser = MagicMock()
        mock_parser.get_node_set.return_value = mock_node_set
        
        mock_rule_service = MagicMock()
        mock_rule_service.get_history_for_ml_inference.return_value = {"history": "data"}
        mock_rule_service.build_rule_set_parser.return_value = mock_parser
        
        mock_inference_engine = MagicMock()
        mock_inference_engine.get_node_set.return_value = mock_node_set
        
        with patch(
            "src.domain.inference.session_service.get_feature_flags",
            return_value=FeatureFlags(ml_optimized_dfs=True),
        ), patch("src.domain.inference.session_service.InferenceEngine") as mock_engine_class, \
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
            
            mock_rule_service.get_history_for_ml_inference.assert_called_once_with("test_rule")
            mock_rule_service.build_rule_set_parser.assert_called_once_with(
                "test_rule",
                {"history": "data"},
            )

    def test_create_session_from_rule_ignores_history_when_ml_dfs_disabled(
        self,
        inference_session_service,
    ):
        mock_node_set = MagicMock()
        mock_node_set.get_node_dictionary.return_value = {"test_goal": MagicMock()}
        mock_parser = MagicMock()
        mock_parser.get_node_set.return_value = mock_node_set
        mock_rule_service = MagicMock()
        mock_rule_service.get_history_for_ml_inference.return_value = {
            "history": "data"
        }
        mock_rule_service.build_rule_set_parser.return_value = mock_parser
        mock_inference_engine = MagicMock()
        mock_inference_engine.get_node_set.return_value = mock_node_set

        with patch(
            "src.domain.inference.session_service.get_feature_flags",
            return_value=FeatureFlags(ml_optimized_dfs=False),
        ), patch(
            "src.domain.inference.session_service.InferenceEngine",
            return_value=mock_inference_engine,
        ), patch("src.domain.inference.session_service.Assessment"):
            inference_session_service.create_session_from_rule(
                rule_name="test_rule",
                target_node_name="test_goal",
                rule_service=mock_rule_service,
            )

        mock_rule_service.get_history_for_ml_inference.assert_called_once_with(
            "test_rule"
        )
        mock_rule_service.build_rule_set_parser.assert_called_once_with(
            "test_rule",
            None,
        )
    
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

    def test_create_session_from_rule_default_history_falls_back_without_records(self, inference_session_service, mock_session_store):
        mock_node_set = MagicMock()
        mock_node_set.get_node_dictionary.return_value = {"test_goal": MagicMock()}

        mock_parser = MagicMock()
        mock_parser.get_node_set.return_value = mock_node_set

        mock_rule_service = MagicMock()
        mock_rule_service.get_history_for_ml_inference.return_value = None
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
        mock_rule_service.get_history_for_ml_inference.assert_called_once_with("test_rule")
        mock_rule_service.build_rule_set_parser.assert_called_once_with("test_rule", None)

    def test_create_session_from_rule_does_not_load_ontology_when_advisory_disabled(self, inference_session_service, mock_session_store):
        mock_node_set = MagicMock()
        mock_node_set.get_node_dictionary.return_value = {"test_goal": MagicMock()}

        mock_parser = MagicMock()
        mock_parser.get_node_set.return_value = mock_node_set

        mock_rule_service = MagicMock()
        mock_rule_service.build_rule_set_parser.return_value = mock_parser

        mock_inference_engine = MagicMock()
        mock_inference_engine.get_node_set.return_value = mock_node_set

        with patch("src.domain.inference.session_service.get_feature_flags", return_value=FeatureFlags(ontology_advisory_enabled=False)), \
             patch("src.domain.inference.session_service.InferenceEngine") as mock_engine_class, \
             patch("src.domain.inference.session_service.Assessment"):
            mock_engine_class.return_value = mock_inference_engine

            session = inference_session_service.create_session_from_rule(
                rule_name="test_rule",
                target_node_name="test_goal",
                rule_service=mock_rule_service,
            )

        assert session.context is None
        assert session.ontology_profile == "off"
        mock_rule_service.get_rule_ontology_data.assert_not_called()
        mock_session_store.save.assert_called_once_with(session)

    def test_create_session_from_rule_records_ontology_advisory_context_when_enabled(self, inference_session_service, mock_session_store):
        mock_node_set = MagicMock()
        mock_node_set.get_node_dictionary.return_value = {"test_goal": MagicMock()}
        mock_node_set.get_input_dictionary.return_value = {"incapacity status": MagicMock()}
        mock_node_set.get_fact_dictionary.return_value = {}

        mock_parser = MagicMock()
        mock_parser.get_node_set.return_value = mock_node_set

        graph_uri = "http://inferra.ai/schema#projection/rule/test_rule"
        mock_rule_service = MagicMock()
        mock_rule_service.build_rule_set_parser.return_value = mock_parser
        mock_rule_service.get_rule_ontology_data.return_value = {
            "graph_uri": graph_uri,
            "source_hash": "source-hash",
            "triples": [
                {
                    "subject": f"{graph_uri}/declaration/incapacity_status",
                    "predicate": "http://inferra.ai/schema#name",
                    "object": "incapacity status",
                },
                {
                    "subject": f"{graph_uri}/declaration/incapacity_status",
                    "predicate": "http://inferra.ai/schema#hasItem",
                    "object": "current employee",
                },
            ],
        }

        mock_inference_engine = MagicMock()
        mock_inference_engine.get_node_set.return_value = mock_node_set

        with patch("src.domain.inference.session_service.get_feature_flags", return_value=FeatureFlags(ontology_advisory_enabled=True)), \
             patch("src.domain.inference.session_service.InferenceEngine") as mock_engine_class, \
             patch("src.domain.inference.session_service.Assessment"):
            mock_engine_class.return_value = mock_inference_engine

            session = inference_session_service.create_session_from_rule(
                rule_name="test_rule",
                target_node_name="test_goal",
                rule_service=mock_rule_service,
            )

        assert session.context is not None
        assert session.context.ontology_profile == "advisory"
        assert session.context.ontology_flags["ontology_advisory_enabled"] is True
        assert session.context.ontology_snapshot_ref == "test_rule:source-hash"
        assert session.context.ontology_snapshot_hash == "source-hash"
        assert session.context.ontology_graph_uris == [graph_uri]
        assert session.context.ontology_binding_count == 1
        suggestions = session.context.ontology_advisory_suggestions["incapacity status"]
        assert suggestions[0]["suggestedValue"] == "current employee"
        assert suggestions[0]["advisoryOnly"] is True
        assert suggestions[0]["altersDeterministicOutcome"] is False
        value_suggestions = session.context.ontology_value_suggestions["incapacity status"]
        assert value_suggestions[0]["suggestedValue"] == "current employee"
        assert value_suggestions[0]["autoAnswerEligible"] is True
        mock_inference_engine.configure_ontology_auto_answer.assert_called_once_with(
            session.context.ontology_value_suggestions,
            ontology_snapshot_hash="source-hash",
        )
        assert mock_session_store.save.call_count == 2

    def test_create_session_from_rule_configures_ontology_reasoner_when_enabled(self, inference_session_service, mock_session_store):
        mock_node_set = MagicMock()
        mock_node_set.get_node_dictionary.return_value = {"test_goal": MagicMock()}
        mock_node_set.get_input_dictionary.return_value = {"vehicle classification": MagicMock()}
        mock_node_set.get_fact_dictionary.return_value = {}

        mock_parser = MagicMock()
        mock_parser.get_node_set.return_value = mock_node_set

        graph_uri = "http://inferra.ai/schema#projection/rule/test_rule"
        mock_rule_service = MagicMock()
        mock_rule_service.build_rule_set_parser.return_value = mock_parser
        mock_rule_service.get_rule_ontology_data.return_value = {
            "graph_uri": graph_uri,
            "source_hash": "source-hash",
            "triples": [
                {
                    "subject": f"{graph_uri}/declaration/vehicle_classification",
                    "predicate": "http://inferra.ai/schema#name",
                    "object": "vehicle classification",
                },
            ],
        }

        mock_inference_engine = MagicMock()
        mock_inference_engine.get_node_set.return_value = mock_node_set

        with patch(
            "src.domain.inference.session_service.get_feature_flags",
            return_value=FeatureFlags(
                ontology_advisory_enabled=False,
                ontology_reasoning=True,
                ontology_reasoning_confidence_threshold=0.9,
                ontology_reasoning_min_hierarchy_depth=2,
                ontology_reasoning_max_closure_depth=8,
            ),
        ), patch("src.domain.inference.session_service.InferenceEngine") as mock_engine_class, \
             patch("src.domain.inference.session_service.Assessment"):
            mock_engine_class.return_value = mock_inference_engine

            session = inference_session_service.create_session_from_rule(
                rule_name="test_rule",
                target_node_name="test_goal",
                rule_service=mock_rule_service,
            )

        assert session.context is not None
        assert session.context.ontology_reasoner_enabled is True
        assert session.context.ontology_reasoning_confidence_threshold == 0.9
        assert session.context.ontology_reasoning_min_hierarchy_depth == 2
        assert session.context.ontology_reasoning_max_closure_depth == 8
        mock_inference_engine.configure_ontology_reasoner.assert_called_once()
        reasoner, ontology_index = (
            mock_inference_engine.configure_ontology_reasoner.call_args.args
        )
        assert reasoner.ontology_snapshot_hash == "source-hash"
        assert reasoner.confidence_threshold == 0.9
        assert ontology_index.subjects_for_label("vehicle classification") == (
            f"{graph_uri}/declaration/vehicle_classification",
        )

    def test_create_session_from_rule_configures_semantic_question_strategy_when_enabled(self, inference_session_service, mock_session_store):
        mock_node_set = MagicMock()
        mock_node_set.get_node_dictionary.return_value = {"test_goal": MagicMock()}
        mock_node_set.get_input_dictionary.return_value = {"medical order signed": MagicMock()}
        mock_node_set.get_fact_dictionary.return_value = {}

        mock_parser = MagicMock()
        mock_parser.get_node_set.return_value = mock_node_set

        graph_uri = "http://inferra.ai/schema#projection/rule/test_rule"
        mock_rule_service = MagicMock()
        mock_rule_service.build_rule_set_parser.return_value = mock_parser
        mock_rule_service.get_rule_ontology_data.return_value = {
            "graph_uri": graph_uri,
            "source_hash": "source-hash",
            "triples": [
                {
                    "subject": f"{graph_uri}/declaration/medical_order_signed",
                    "predicate": "http://inferra.ai/schema#name",
                    "object": "medical order signed",
                },
            ],
        }

        mock_inference_engine = MagicMock()
        mock_inference_engine.get_node_set.return_value = mock_node_set

        with patch(
            "src.domain.inference.session_service.get_feature_flags",
            return_value=FeatureFlags(
                ontology_advisory_enabled=False,
                ontology_reasoning=False,
                ontology_question_strategy=True,
            ),
        ), patch("src.domain.inference.session_service.InferenceEngine") as mock_engine_class, \
             patch("src.domain.inference.session_service.Assessment"):
            mock_engine_class.return_value = mock_inference_engine

            session = inference_session_service.create_session_from_rule(
                rule_name="test_rule",
                target_node_name="test_goal",
                rule_service=mock_rule_service,
            )

        assert session.context is not None
        assert session.context.question_strategy_name == "semantic_ontology"
        mock_inference_engine.set_question_strategy.assert_called_once()
        strategy = mock_inference_engine.set_question_strategy.call_args.args[0]
        assert isinstance(strategy, SemanticQuestionStrategy)
        mock_inference_engine.configure_ontology_reasoner.assert_not_called()

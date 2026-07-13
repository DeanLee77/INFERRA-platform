"""
Inference Session Service Module.
Orchestrates inference session lifecycle and state management.
"""

import uuid
from typing import Any, Iterable, Mapping, Optional, Tuple, TYPE_CHECKING

from src.domain.inference.session import InferenceSession
from src.domain.inference.inference_engine import InferenceEngine
from src.domain.inference.assessment import Assessment
from src.domain.inference.semantic_question_strategy import SemanticQuestionStrategy
from src.domain.nodes.node_set import NodeSet
from src.domain.reasoning.semantic_fact_enricher import (
    OntologyIndex,
    OntologyTriple,
    build_ontology_constraint_suggestions,
    build_ontology_value_suggestions,
    build_semantic_suggestions,
)
from src.domain.reasoning.ontology_reasoner import OntologyReasoner
from src.domain.session.inference_context import InferenceContext
from src.domain.state.feature_flags import (
    FeatureFlags,
    feature_flags_from_snapshot,
    get_feature_flags,
    ontology_flags_snapshot,
)
from src.ports.session_store_port import SessionStorePort
from src.infrastructure.logging_config import get_logger

if TYPE_CHECKING:
    from src.services.rule_service import RuleService

_logger = get_logger(__name__)


class InferenceSessionService:
    """
    Service for managing inference sessions.
    
    This service encapsulates the logic for:
    - Creating new inference sessions with unique IDs
    - Retrieving existing sessions
    - Managing session lifecycle
    
    It replaces the old Flask session-based approach with explicit
    session IDs that can be tracked by the client.
    """
    
    def __init__(self, session_store: SessionStorePort):
        """
        Initialize the session service.
        
        Args:
            session_store: The session storage backend
        """
        self._store = session_store
    
    @staticmethod
    def generate_session_id() -> str:
        """
        Generate a unique session ID.

        Returns:
            A UUID-based session ID string
        """
        return str(uuid.uuid4())

    @staticmethod
    def _snapshot_and_freeze_flags(
        ontology_profile: Optional[str] = None,
        ontology_flags: Optional[Mapping[str, Any]] = None,
    ) -> Tuple[FeatureFlags, str]:
        """
        Read the current global FeatureFlags, build a fresh per-session instance
        from that snapshot, and freeze it. Per-session instance means a later
        change to the global flags can't leak into a session that started before
        the change — that's the start-of-session-sticky guarantee from plan §6.

        Returns:
            Tuple of frozen per-session FeatureFlags and selected ontology profile
        """
        global_flags = get_feature_flags()
        snapshot = global_flags.snapshot()
        session_flags, selected_profile = feature_flags_from_snapshot(
            snapshot,
            ontology_profile=ontology_profile,
            ontology_flags=ontology_flags,
        )
        session_flags.freeze()
        return session_flags, selected_profile
    
    def create_session(
        self,
        rule_name: str,
        target_node_name: str,
        node_set: NodeSet,
        history_dict: Optional[dict] = None,
        owner_id: Optional[str] = None,
        ontology_profile: Optional[str] = None,
        ontology_flags: Optional[Mapping[str, Any]] = None,
        llm_configuration: Optional[Mapping[str, Any]] = None,
    ) -> InferenceSession:
        """
        Create a new inference session.
        
        This method:
        1. Creates a new InferenceEngine with the provided NodeSet
        2. Creates a new Assessment for the target node
        3. Stores the session and returns it with a unique ID
        
        Args:
            rule_name: Name of the rule being evaluated
            target_node_name: Name of the target/goal node
            node_set: The parsed NodeSet containing rules
            history_dict: Optional history data for ML inference
            
        Returns:
            A new InferenceSession with unique ID
            
        Raises:
            ValueError: If target_node_name doesn't exist in node_set
        """
        # Validate target node exists
        if target_node_name not in node_set.get_node_dictionary():
            raise ValueError(
                f"Target node '{target_node_name}' does not exist in rule '{rule_name}'"
            )

        # Snapshot + freeze feature flags at session start so they can't flip
        # mid-session — see plan §6 mid-session-flip risk row.
        session_flags, selected_ontology_profile = self._snapshot_and_freeze_flags(
            ontology_profile,
            ontology_flags,
        )

        # Create inference engine
        inference_engine = InferenceEngine(node_set, feature_flags=session_flags)
        inference_engine.get_node_set().set_node_set_name(rule_name)

        # Create assessment
        assessment = Assessment(node_set, target_node_name)

        # Add assessment to engine
        inference_engine.add_assessment_into_assessment_list(assessment)

        # Create session
        session_id = self.generate_session_id()
        session = InferenceSession(
            session_id=session_id,
            rule_name=rule_name,
            target_node_name=target_node_name,
            inference_engine=inference_engine,
            assessment=assessment,
            feature_flags=session_flags,
            ontology_profile=selected_ontology_profile,
            ontology_profile_source=(
                "request" if ontology_profile or ontology_flags else "environment"
            ),
            llm_configuration=dict(llm_configuration or {}),
            owner_id=owner_id,
        )
        
        # Store session
        self._store.save(session)
        
        _logger.info(
            f"Created inference session: {session_id} "
            f"(rule={rule_name}, target={target_node_name})"
        )
        
        return session

    def save_session(self, session: InferenceSession) -> None:
        """Persist an existing session after request-time state mutation."""
        self._store.save(session)
    
    def get_session(self, session_id: str) -> Optional[InferenceSession]:
        """
        Retrieve an existing session.
        
        Args:
            session_id: The unique session identifier
            
        Returns:
            InferenceSession if found, None otherwise
        """
        return self._store.get(session_id)

    def list_sessions(self) -> list[InferenceSession]:
        """Return currently stored inference sessions."""
        sessions: list[InferenceSession] = []
        for session_id in self._store.list_sessions():
            session = self._store.get(session_id)
            if session is not None:
                sessions.append(session)
        return sessions
    
    def get_or_create_session(
        self,
        session_id: Optional[str],
        rule_name: str,
        target_node_name: str,
        node_set: NodeSet,
        history_dict: Optional[dict] = None,
        ontology_profile: Optional[str] = None,
        ontology_flags: Optional[Mapping[str, Any]] = None,
    ) -> Tuple[InferenceSession, bool]:
        """
        Get an existing session or create a new one.
        
        Args:
            session_id: Existing session ID (if any)
            rule_name: Name of the rule being evaluated
            target_node_name: Name of the target/goal node
            node_set: The parsed NodeSet containing rules
            history_dict: Optional history data for ML inference
            
        Returns:
            Tuple of (InferenceSession, was_created)
            - was_created is True if a new session was created
        """
        if session_id:
            session = self.get_session(session_id)
            if session and session.inference_engine.get_node_set().get_node_set_name() == rule_name:
                # Existing session is valid for this rule
                return session, False
        
        # Need to create new session
        session = self.create_session(
            rule_name=rule_name,
            target_node_name=target_node_name,
            node_set=node_set,
            history_dict=history_dict,
            ontology_profile=ontology_profile,
            ontology_flags=ontology_flags,
        )
        return session, True
    
    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session.
        
        Args:
            session_id: The unique session identifier
            
        Returns:
            True if deleted, False if not found
        """
        return self._store.delete(session_id)
    
    def session_exists(self, session_id: str) -> bool:
        """
        Check if a session exists.
        
        Args:
            session_id: The unique session identifier
            
        Returns:
            True if session exists
        """
        return self._store.exists(session_id)
    
    def clear_expired_sessions(self, max_age_seconds: int = 3600) -> int:
        """
        Clear sessions older than the specified age.
        
        Args:
            max_age_seconds: Maximum session age in seconds (default: 1 hour)
            
        Returns:
            Number of sessions cleared
        """
        return self._store.clear_expired(max_age_seconds)

    def create_session_from_rule(
        self,
        rule_name: str,
        target_node_name: str,
        rule_service: 'RuleService',
        use_history: bool = True,
        owner_id: Optional[str] = None,
        ontology_profile: Optional[str] = None,
        ontology_flags: Optional[Mapping[str, Any]] = None,
        llm_configuration: Optional[Mapping[str, Any]] = None,
    ) -> InferenceSession:
        """
        Create a new inference session by parsing a rule.
        
        This is a convenience method that:
        1. Uses RuleService to parse the rule and build a NodeSet
        2. Uses history for ML-enhanced inference by default
        3. Creates and stores the inference session
        
        Args:
            rule_name: Name of the rule to parse
            target_node_name: Name of the target/goal node
            rule_service: RuleService instance for parsing
            use_history: Whether to use historical data for ML inference
            
        Returns:
            A new InferenceSession with unique ID
            
        Raises:
            LookupError: If rule is not found
            ValueError: If target_node_name doesn't exist in the rule
        """
        # Get history dict if ML inference is requested
        history_dict = None
        if use_history:
            history_dict = rule_service.get_history_for_ml_inference(rule_name)
        
        # Build the node set
        parser = rule_service.build_rule_set_parser(rule_name, history_dict)
        node_set = parser.get_node_set()
        
        # Create the session
        session = self.create_session(
            rule_name=rule_name,
            target_node_name=target_node_name,
            node_set=node_set,
            history_dict=history_dict,
            owner_id=owner_id,
            ontology_profile=ontology_profile,
            ontology_flags=ontology_flags,
            llm_configuration=llm_configuration,
        )
        if self._attach_ontology_advisory_context(session, node_set, rule_service):
            self._store.save(session)
        return session

    def _attach_ontology_advisory_context(
        self,
        session: InferenceSession,
        node_set: NodeSet,
        rule_service: 'RuleService',
    ) -> bool:
        flags = session.feature_flags
        if flags is None or not (
            flags.ontology_advisory_enabled
            or flags.ontology_reasoning
            or flags.ontology_question_strategy
        ):
            return False

        assessment_state = session.inference_engine.get_assessment_state()
        context = InferenceContext(
            session_id=session.session_id,
            rule_name=session.rule_name,
            target=session.target_node_name,
            mandatory=list(assessment_state.get_mandatory_list()),
            fact_store=assessment_state.get_fact_store(),
            ontology_profile=session.ontology_profile,
            ontology_profile_source=session.ontology_profile_source,
            ontology_flags=ontology_flags_snapshot(flags),
        )

        try:
            ontology = rule_service.get_rule_ontology_data(session.rule_name)
            triples = tuple(_ontology_triples_from_payload(ontology))
            ontology_index = OntologyIndex(triples)
            graph_uri = str(ontology.get("graph_uri") or "compiled_rule_projection")
            snapshot_hash = str(ontology.get("source_hash") or "")
            snapshot_ref = (
                f"{session.rule_name}:{snapshot_hash}"
                if snapshot_hash
                else f"{session.rule_name}:compiled"
            )
            report, suggestions = build_semantic_suggestions(
                _candidate_fact_names(node_set),
                triples,
                source_graph_uri=graph_uri,
                ontology_snapshot_ref=snapshot_ref,
                ontology_snapshot_hash=snapshot_hash or None,
            )
            trace = report.to_trace()
            context.ontology_snapshot_ref = snapshot_ref
            context.ontology_snapshot_hash = snapshot_hash or None
            context.ontology_graph_uris = [graph_uri]
            context.ontology_reasoner_enabled = flags.ontology_reasoning
            context.ontology_reasoning_confidence_threshold = (
                flags.ontology_reasoning_confidence_threshold
            )
            context.ontology_reasoning_min_hierarchy_depth = (
                flags.ontology_reasoning_min_hierarchy_depth
            )
            context.ontology_reasoning_max_closure_depth = (
                flags.ontology_reasoning_max_closure_depth
            )
            context.ontology_binding_count = trace["bindingCount"]
            context.ontology_binding_ambiguity_count = trace["ambiguityCount"]
            context.ontology_missing_binding_count = trace["missingCount"]
            context.ontology_advisory_trace = [trace]
            context.ontology_advisory_suggestions = {
                fact_name: [item.to_dict() for item in fact_suggestions]
                for fact_name, fact_suggestions in suggestions.items()
                if fact_suggestions
            }
            value_suggestions = build_ontology_value_suggestions(
                report,
                triples,
                ontology_snapshot_ref=snapshot_ref,
                ontology_snapshot_hash=snapshot_hash or None,
            )
            constraint_suggestions = build_ontology_constraint_suggestions(
                report,
                triples,
                ontology_snapshot_ref=snapshot_ref,
                ontology_snapshot_hash=snapshot_hash or None,
            )
            context.ontology_value_suggestions = {
                fact_name: [item.to_dict() for item in fact_suggestions]
                for fact_name, fact_suggestions in value_suggestions.items()
                if fact_suggestions
            }
            context.ontology_constraint_suggestions = {
                fact_name: [item.to_dict() for item in fact_suggestions]
                for fact_name, fact_suggestions in constraint_suggestions.items()
                if fact_suggestions
            }
            session.inference_engine.configure_ontology_auto_answer(
                context.ontology_value_suggestions,
                ontology_snapshot_hash=context.ontology_snapshot_hash,
            )
            ontology_reasoner = OntologyReasoner(
                source_graph_uri=graph_uri,
                ontology_snapshot_ref=snapshot_ref,
                ontology_snapshot_hash=snapshot_hash or None,
                confidence_threshold=(
                    flags.ontology_reasoning_confidence_threshold
                ),
                min_hierarchy_depth=(
                    flags.ontology_reasoning_min_hierarchy_depth
                ),
                max_closure_depth=(
                    flags.ontology_reasoning_max_closure_depth
                ),
            )
            if flags.ontology_reasoning:
                session.inference_engine.configure_ontology_reasoner(
                    ontology_reasoner,
                    ontology_index,
                )
            if flags.ontology_question_strategy:
                session.inference_engine.set_question_strategy(
                    SemanticQuestionStrategy(
                        reasoner=ontology_reasoner,
                        ontology_index=ontology_index,
                        fact_store=assessment_state.get_fact_store(),
                        value_suggestions=context.ontology_value_suggestions,
                        allow_pruning=flags.ontology_reasoning,
                    )
                )
                context.question_strategy_name = "semantic_ontology"
            _logger.info(
                "ontology_advisory_snapshot_attached",
                session_id=session.session_id,
                rule_name=session.rule_name,
                source_hash=context.ontology_snapshot_hash,
                binding_count=context.ontology_binding_count,
                ambiguity_count=context.ontology_binding_ambiguity_count,
                missing_count=context.ontology_missing_binding_count,
            )
        except Exception as exc:
            context.ontology_snapshot_ref = f"{session.rule_name}:unavailable"
            context.ontology_reasoner_enabled = flags.ontology_reasoning
            context.ontology_advisory_trace = [
                {
                    "status": "unavailable",
                    "error": str(exc),
                    "bindingCount": 0,
                    "ambiguityCount": 0,
                    "missingCount": 0,
                }
            ]
            _logger.warning(
                "ontology_advisory_snapshot_failed",
                session_id=session.session_id,
                rule_name=session.rule_name,
                exc_info=True,
            )

        session.context = context
        return True


def _ontology_triples_from_payload(payload: dict[str, Any]) -> Iterable[OntologyTriple]:
    for item in payload.get("triples", ()):
        if isinstance(item, dict):
            subject = item.get("subject")
            predicate = item.get("predicate")
            obj = item.get("object")
            if subject and predicate and obj is not None:
                yield (str(subject), str(predicate), str(obj))
            continue
        if isinstance(item, (tuple, list)) and len(item) == 3:
            subject, predicate, obj = item
            yield (str(subject), str(predicate), str(obj))


def _candidate_fact_names(node_set: NodeSet) -> Iterable[str]:
    names: set[str] = set()

    for accessor_name in ("get_input_dictionary", "get_fact_dictionary"):
        accessor = getattr(node_set, accessor_name, None)
        if callable(accessor):
            values = accessor()
            if isinstance(values, dict):
                names.update(str(name) for name in values)

    node_dictionary = node_set.get_node_dictionary()
    for node_name, node in node_dictionary.items():
        names.add(str(node_name))
        for accessor_name in ("get_node_name", "get_variable_name"):
            accessor = getattr(node, accessor_name, None)
            if callable(accessor):
                value = accessor()
                if isinstance(value, str) and value:
                    names.add(value)

    return sorted(names)

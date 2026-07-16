"""
Inference Engine Module.
Core engine for INFERRA rule evaluation and backward chaining.
Implements access levels and strong typing where appropriate.

Phase 2.5 (WS-1): Hot-path operations use DependencyGraphPort exclusively.
No direct get_dependency_matrix() or get_node_id() calls remain.
"""

import json
from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional, Set, Tuple
from src.domain.inference.assessment import Assessment
from src.domain.inference.assessment_state import AssessmentState
from src.domain.fact_values import FactValue, FactValueType
from src.domain.inference.assessments import Assessments
from src.domain.inference.question_resolver import QuestionResolver
from src.domain.nodes.comparison_line import ComparisonLine
from src.domain.graph.dependency_type import DependencyType
from src.domain.nodes.line_type import LineType
from src.domain.nodes.node import Node
from src.domain.nodes.node_set import NodeSet
from src.domain.nodes.value_conclusion_line import ValueConclusionLine
from src.domain.reasoning.ontology_reasoner import OntologyReasoner
from src.domain.reasoning.semantic_fact_enricher import OntologyIndex
from src.domain.state.fact_source import FactSource
from src.domain.state.feature_flags import FeatureFlags
from src.ports.dependency_graph_port import DependencyGraphPort
from src.ports.question_strategy_port import QuestionStrategyPort
from src.infrastructure.logging_config import get_logger

_logger = get_logger(__name__)


def _noop_question_callback(_: Any) -> None:
    """Default callback used when no external question sink is attached."""
    return None


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class InferenceEngine:
    """
    InferenceEngine manages rule evaluation, backward chaining, and user questioning.
    
    Access Levels:
    - Public: API methods for external use
    - Protected: Internal helpers (single underscore)
    - Private: Internal state (double underscore)
    """
    
    # -------------------------------------------------------------------------
    # Private Access Level: Instance Variables (Name Mangling)
    # -------------------------------------------------------------------------
    def __init__(
        self,
        node_set: Optional[NodeSet] = None,
        feature_flags: Optional[FeatureFlags] = None,
        question_strategy: Optional[QuestionStrategyPort] = None,
    ):
        """
        Public Constructor: Initializes InferenceEngine.

        Args:
            node_set: Optional NodeSet containing rules
            feature_flags: Optional FeatureFlags snapshot. When None, defaults
                to a fresh FeatureFlags reading current env. Sessions should
                pass an already-frozen instance so flags can't flip mid-session.
        """
        # Private instance variables (initialized in __init__ to avoid shared state)
        self.__node_set: Optional[NodeSet] = node_set
        self.__target_node: Optional[Node] = None
        self.__ast: AssessmentState = self._new_assessment_state()
        self.__ass: Assessment = Assessment()
        self.__asses: Assessments = Assessments()
        self.__node_fact_list: List[Node] = list()
        self.__question_resolver: QuestionResolver = QuestionResolver(
            _noop_question_callback,
            ontology_default_lookup=self._ontology_default_fact_value_for_node,
        )
        self.__question_strategy: Optional[QuestionStrategyPort] = question_strategy
        self.__feature_flags: FeatureFlags = feature_flags if feature_flags is not None else FeatureFlags()
        self.__dependency_graph: Optional[DependencyGraphPort] = None
        self.__branch_prune_trace: List[Dict[str, Any]] = []
        self.__pruned_question_flow_nodes: Set[str] = set()
        self.__ontology_value_suggestions: Dict[str, List[Dict[str, Any]]] = {}
        self.__ontology_snapshot_hash: Optional[str] = None
        self.__ontology_auto_answer_trace: List[Dict[str, Any]] = []
        self.__ontology_reasoner: Optional[OntologyReasoner] = None
        self.__ontology_index: Optional[OntologyIndex] = None
        self.__ontology_materialization_trace: List[Dict[str, Any]] = []
        self.__ontology_derived_facts: List[str] = []
        self.__deferred_question_names: Set[str] = set()

        if node_set is not None:
            self._initialize_from_node_set(node_set)
            self._select_graph_backend(node_set)
            self._discover_global_mandatory_obligations()

        _logger.info(
            "InferenceEngine initialised "
            f"(use_hypergraph={self.__feature_flags.use_hypergraph}, "
            f"legacy_iterate={self.__feature_flags.legacy_iterate}, "
            f"layered_memory={self.__feature_flags.layered_memory}, "
            f"graph_backend={'hypergraph' if self.__dependency_graph is not None else 'none'})"
        )

    # -------------------------------------------------------------------------
    # Public Access Level: Feature-Flag & Graph Backend Accessors
    # -------------------------------------------------------------------------
    def get_feature_flags(self) -> FeatureFlags:
        """
        Public API: Returns the FeatureFlags snapshot governing this engine's behaviour.

        Returns:
            FeatureFlags instance (typically frozen at session start)
        """
        return self.__feature_flags

    def get_dependency_graph(self) -> Optional[DependencyGraphPort]:
        """
        Public API: Returns the canonical dependency graph used by the engine.

        Returns:
            DependencyGraphPort instance, or None when no graph is available
        """
        return self.__dependency_graph

    def get_branch_prune_trace(self) -> List[Dict[str, Any]]:
        """
        Public API: Returns audit events for skipped inactive branch questions.
        """
        return [dict(item) for item in self.__branch_prune_trace]

    def configure_ontology_auto_answer(
        self,
        value_suggestions: Dict[str, List[Dict[str, Any]]],
        *,
        ontology_snapshot_hash: Optional[str],
    ) -> None:
        """
        Public API: Installs frozen session ontology default candidates.
        """
        self.__ontology_value_suggestions = {
            str(fact_name): [dict(item) for item in suggestions]
            for fact_name, suggestions in value_suggestions.items()
        }
        self.__ontology_snapshot_hash = ontology_snapshot_hash

    def get_ontology_auto_answer_trace(self) -> List[Dict[str, Any]]:
        """
        Public API: Returns audit events for ontology auto-answer decisions.
        """
        return [dict(item) for item in self.__ontology_auto_answer_trace]

    def configure_ontology_reasoner(
        self,
        reasoner: OntologyReasoner,
        ontology_index: OntologyIndex,
    ) -> None:
        """
        Public API: Installs the frozen session ontology materializer.
        """
        self.__ontology_reasoner = reasoner
        self.__ontology_index = ontology_index

    def get_ontology_materialization_trace(self) -> List[Dict[str, Any]]:
        """
        Public API: Returns audit events for ontology materialization decisions.
        """
        return [dict(item) for item in self.__ontology_materialization_trace]

    def get_ontology_derived_facts(self) -> List[str]:
        """
        Public API: Returns names of ontology-derived INFERRED facts.
        """
        return list(self.__ontology_derived_facts)

    def set_question_strategy(
        self,
        question_strategy: Optional[QuestionStrategyPort],
    ) -> None:
        """
        Public API: Installs an optional advisory question strategy.

        Passing None restores the legacy conservative QuestionResolver path.
        """
        self.__question_strategy = question_strategy

    def get_semantic_question_strategy_trace(self) -> List[Dict[str, Any]]:
        """
        Public API: Returns audit events for ontology-guided question selection.
        """
        trace_getter = getattr(self.__question_strategy, "get_trace", None)
        if not callable(trace_getter):
            return []
        return [dict(item) for item in trace_getter()]

    def defer_question(self, question_name: str) -> None:
        """
        Public API: Marks a question as deferred for this session.

        Deferred questions are skipped without asserting an UNKNOWN fact. This is
        intended for post-decision semantic completion, where the generated TTL
        records the gap as metadata.
        """
        normalized = str(question_name or "").strip()
        if not normalized:
            return
        self.__deferred_question_names.add(normalized)
        self.__ass.set_node_to_be_asked(None)
        self.__ass.set_aux_node_to_be_asked(None)

    def get_deferred_questions(self) -> List[str]:
        """Return question names deferred during this session."""
        return sorted(self.__deferred_question_names)

    # -------------------------------------------------------------------------
    # Protected Access Level: Internal Helpers (Single Underscore)
    # -------------------------------------------------------------------------
    def _initialize_from_node_set(self, node_set: NodeSet) -> None:
        """
        Protected Helper: Initializes engine state from NodeSet.

        Args:
            node_set: NodeSet containing rules and facts
        """
        temp_fact_dict = node_set.get_fact_dictionary() if node_set is not None else {}

        if len(temp_fact_dict) > 0:
            for key, value in temp_fact_dict.items():
                self.__ast.set_fact(key, value, source=FactSource.ASSERTED)

    def _new_assessment_state(self) -> AssessmentState:
        """
        Protected Helper: Creates new AssessmentState instance.

        Returns:
            New AssessmentState object
        """
        return AssessmentState()

    def _select_graph_backend(self, node_set: NodeSet) -> None:
        """
        Protected Helper: Build the graph backend for hot-path operations.

        Phase 2.5 (WS-1): Always builds the graph — the engine depends on
        DependencyGraphPort for all hot-path traversal. Prefers the canonical
        graph from NodeSet when available. Legacy matrix payloads are converted
        by NodeSet.set_dependency_matrix().
        """
        canonical_graph = node_set.get_graph()
        if canonical_graph is not None:
            self.__dependency_graph = canonical_graph
            _logger.info(
                "Graph backend: using canonical HyperAdjacencyGraph from NodeSet"
            )
            return

        _logger.warning("NodeSet lacks canonical dependency graph")

    def _discover_global_mandatory_obligations(self) -> None:
        if self.__dependency_graph is None:
            return

        for parent_name, child_name, dep_type_int in self.__dependency_graph.edges():
            if dep_type_int & DependencyType.get_mandatory():
                self.__ast.add_item_to_mandatory_list(child_name)
                removed_from: List[str] = []
                if (
                    child_name not in self.__ast.get_inclusive_list()
                    and child_name not in self.__ast.get_exclusive_list()
                ):
                    self.__ast.get_inclusive_list().append(child_name)
                    removed_from.append("not_in_inclusive_list")
                self._record_question_flow_event(
                    child_name,
                    parent_name=parent_name,
                    action="retained",
                    reason="global_mandatory_obligation",
                    removed_from=removed_from,
                )

    def _handle_value_conclusion_line_true_case(
        self,
        value_node: Node,
        is_plain_statement_format: bool,
        node_fact_value_in_string: str,
    ) -> None:
        """
        Protected Helper: Handles TRUE case for ValueConclusionLine.
        
        Args:
            value_node: The value conclusion node
            is_plain_statement_format: Whether node is plain statement
            node_fact_value_in_string: Node fact value as string
        """
        self.__ast.set_fact(value_node.get_node_name(), FactValue(True))
        if not is_plain_statement_format:
            if node_fact_value_in_string in self.__ast.get_working_memory().keys():
                self.__ast.set_fact(
                    value_node.get_variable_name(),
                    self.__ast.get_working_memory()[node_fact_value_in_string]
                )
            else:
                self.__ast.set_fact(value_node.get_variable_name(), value_node.get_fact_value(), value_node)
            self.__ast.add_item_to_summary_list(value_node.get_variable_name())

    def _handle_value_conclusion_line_false_case(
        self,
        value_node: Node,
        is_plain_statement_format: bool,
        node_fact_value_in_string: str,
    ) -> None:
        """
        Protected Helper: Handles FALSE case for ValueConclusionLine.
        
        Args:
            value_node: The value conclusion node
            is_plain_statement_format: Whether node is plain statement
            node_fact_value_in_string: Node fact value as string
        """
        self.__ast.set_fact(value_node.get_node_name(), FactValue(False))
        if not is_plain_statement_format:
            if node_fact_value_in_string in self.__ast.get_working_memory().keys():
                fact_value_from_working_memory: FactValue = self.__ast.get_working_memory()[node_fact_value_in_string]
                fact_key = "NOT " + str(self.__ast.get_working_memory()[node_fact_value_in_string])
                if fact_value_from_working_memory.get_value_type() is FactValueType.LIST:
                    fact_value_from_working_memory.get_value().append(FactValue(fact_key))
                    self.__ast.set_fact(value_node.get_variable_name(), fact_value_from_working_memory)
                else:
                    fact_value_list = list()
                    fact_value_list.append(self.__ast.get_working_memory()[node_fact_value_in_string])
                    fact_value_list.append(FactValue(fact_key))
                    self.__ast.set_fact(value_node.get_variable_name(), FactValue(fact_value_list, FactValueType.LIST))
            else:
                self.__ast.set_fact(
                    value_node.get_variable_name(),
                    FactValue("NOT " + node_fact_value_in_string),
                    value_node
                )
            self.__ast.add_item_to_summary_list(value_node.get_variable_name())

    def _type_already_set(self, input_fact_value: FactValue) -> bool:
        """
        Protected Helper: Checks if fact value type is already defined.
        
        Args:
            input_fact_value: FactValue to check
            
        Returns:
            True if type is already set
        """
        has_already_set_type = False
        fact_value_type: FactValueType = input_fact_value.get_value_type()

        if fact_value_type in [FactValueType.DEFI_STRING, FactValueType.INTEGER, 
                               FactValueType.DOUBLE, FactValueType.DATE, FactValueType.BOOLEAN,
                               FactValueType.GUID, FactValueType.URL, FactValueType.HASH]:
            has_already_set_type = True

        return has_already_set_type

    def _has_any_or_child_evaluated(self, parent_node_name: str, or_child_names: List[str]) -> bool:
        """
        Protected Helper: Checks if any OR child has been evaluated.
        
        Args:
            parent_node_name: Parent node name
            or_child_names: List of OR child node names
            
        Returns:
            True if any OR child is evaluated
        """
        if self.__node_set is None or self.__dependency_graph is None:
            return False

        node_dict = self.__node_set.get_node_dictionary()
        wm = self.__ast.get_working_memory()

        any_or_child_evaluated: bool = any(
            (child_name in wm
             and self.__dependency_graph.get_dependency_type(parent_node_name, child_name) != -1
             and self.__dependency_graph.get_dependency_type(parent_node_name, child_name)
             & DependencyType.get_mandatory() == DependencyType.get_mandatory())
            or (child_name in node_dict and node_dict[child_name].get_variable_name() in wm)
            for child_name in or_child_names
        )

        return any_or_child_evaluated

    def _has_all_and_child_evaluated(self, and_child_names: List[str]) -> bool:
        """
        Protected Helper: Checks if all AND children have been evaluated.
        
        Args:
            and_child_names: List of AND child node names
            
        Returns:
            True if all AND children are evaluated
        """
        if self.__node_set is None:
            return False

        node_dict = self.__node_set.get_node_dictionary()

        all_and_child_evaluated: bool = all(
            child_name in node_dict and node_dict[child_name].get_variable_name()
            in self.__ast.get_working_memory().keys()
            for child_name in and_child_names
        )

        return all_and_child_evaluated

    def _is_deterministic_fact(self, fact_name: str) -> bool:
        """
        Protected Helper: Returns whether a fact can drive rule truth.

        SEMANTIC-only ontology facts are advisory: they can guide question
        strategy and display provenance, but they must not satisfy rule
        guardrails or change deterministic boolean outcomes.
        """
        sources = self.__ast.get_fact_sources(fact_name)
        return bool(sources) and sources != {FactSource.SEMANTIC}

    def _get_deterministic_fact(self, fact_name: str) -> Optional[FactValue]:
        """
        Protected Helper: Gets a rule-authoritative fact if one exists.
        """
        if not self._is_deterministic_fact(fact_name):
            return None
        return self.__ast.get_working_memory().get(fact_name)

    def _get_deterministic_working_memory(self) -> Dict[str, FactValue]:
        """
        Protected Helper: Builds the working-memory view used for rule truth.
        """
        return {
            name: value
            for name, value in self.__ast.get_working_memory().items()
            if self._is_deterministic_fact(name)
        }

    def _has_deterministic_child_answer(self, child_name: str) -> bool:
        """
        Protected Helper: Checks node and answer keys for authoritative facts.
        """
        if self._get_deterministic_fact(child_name) is not None:
            return True
        if self.__node_set is None:
            return False

        child_node = self.__node_set.get_node_dictionary().get(child_name)
        if child_node is None:
            return False

        return any(
            self._get_deterministic_fact(key) is not None
            for key in self._answer_keys_for_node(child_node)
        )

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (NodeSet)
    # -------------------------------------------------------------------------
    def set_node_set(self, node_set: NodeSet) -> None:
        """
        Public API: Sets the NodeSet for the engine.
        
        Args:
            node_set: NodeSet containing rules
        """
        self.__node_set = node_set
        self.__ast = self._new_assessment_state()
        self._initialize_from_node_set(node_set)
        self._select_graph_backend(node_set)
        self._discover_global_mandatory_obligations()

    def get_node_set(self) -> Optional[NodeSet]:
        """
        Public API: Returns the current NodeSet.
        
        Returns:
            Current NodeSet or None
        """
        return self.__node_set

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (AssessmentState)
    # -------------------------------------------------------------------------
    def get_assessment_state(self) -> AssessmentState:
        """
        Public API: Returns the current AssessmentState.
        
        Returns:
            Current AssessmentState
        """
        return self.__ast

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Assessments)
    # -------------------------------------------------------------------------
    def set_assessments(self, asses: Assessments) -> None:
        """
        Public API: Sets the Assessments collection.
        
        Args:
            asses: Assessments collection
        """
        self.__asses = asses

    def get_assessments(self) -> Assessments:
        """
        Public API: Returns the Assessments collection.
        
        Returns:
            Current Assessments collection
        """
        return self.__asses

    def add_assessment_into_assessment_list(self, assessment: Assessment) -> None:
        """
        Public API: Adds an assessment to the collection.
        
        Args:
            assessment: Assessment to add
        """
        self.__asses.add_assessment(assessment)
        self.__ass = assessment

    def get_assessment_of_rule(self, goal_rule_name: str) -> Optional[Assessment]:
        """
        Public API: Gets an assessment by rule name.
        
        Args:
            goal_rule_name: Name of the goal rule
            
        Returns:
            Assessment or None
        """
        return self.__asses.get_assessment(goal_rule_name)

    def set_assessment(self, ass: Assessment) -> None:
        """
        Public API: Sets the current assessment.
        
        Args:
            ass: Assessment to set
        """
        self.__ass = ass

    def get_assessment(self) -> Assessment:
        """
        Public API: Returns the current assessment.
        
        Returns:
            Current Assessment
        """
        return self.__ass

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Question Handling)
    # -------------------------------------------------------------------------
    def get_questions_from_node_to_be_asked(self, node: Optional[Node]) -> List[str]:
        """
        Public API: Returns the user-facing question keys for an askable node.

        The rule graph asks nodes, but answers are stored under variable names
        such as an INPUT declaration key. For example, the node
        "service type IS IN LIST: DVA operational service type" must ask for
        and store the answer under "service type".

        Args:
            node: Node selected by backward chaining

        Returns:
            List of question names to present to the caller
        """
        question_name = self._question_name_for_node(node)
        return [question_name] if question_name else []

    def find_type_of_element_to_be_asked(
        self,
        node: Optional[Node],
    ) -> Dict[str, FactValueType]:
        """
        Public API: Returns expected value types for a selected node.

        The map includes the question key used for answer submission and, when
        different, the node name itself for callers that need the result type of
        a goal node.

        Args:
            node: Node selected by backward chaining

        Returns:
            Mapping from question or node name to FactValueType
        """
        if node is None:
            return {}

        question_names = self.get_questions_from_node_to_be_asked(node)
        question_types = {
            question_name: self._infer_question_value_type(node, question_name)
            for question_name in question_names
        }

        node_name = node.get_node_name()
        if isinstance(node_name, str) and node_name and node_name not in question_types:
            question_types[node_name] = self._infer_node_value_type(node)

        return question_types

    def _question_name_for_node(self, node: Optional[Node]) -> Optional[str]:
        """
        Protected Helper: Derives the answer key for an askable node.
        """
        if node is None:
            return None

        if node.get_line_type() == LineType.COMPARISON and hasattr(node, "get_lhs"):
            lhs = node.get_lhs()
            if isinstance(lhs, str) and lhs:
                return lhs

        variable_name = node.get_variable_name()
        if isinstance(variable_name, str) and variable_name:
            return variable_name

        node_name = node.get_node_name()
        if isinstance(node_name, str) and node_name:
            return node_name
        return None

    def _declared_value_type(self, name: str) -> Optional[FactValueType]:
        """
        Protected Helper: Finds a declared INPUT/FIXED type by variable name.
        """
        if self.__node_set is None:
            return None

        declaration_names = {name}
        for dictionary in (
            self.__node_set.get_input_dictionary(),
            self.__node_set.get_fact_dictionary(),
        ):
            for declared_name in dictionary.keys():
                if name.endswith(f"  {declared_name}"):
                    declaration_names.add(declared_name)

        for declaration_name in sorted(declaration_names, key=len, reverse=True):
            for declaration in (
                self.__node_set.get_input_dictionary().get(declaration_name),
                self.__node_set.get_fact_dictionary().get(declaration_name),
            ):
                if hasattr(declaration, "get_value_type"):
                    value_type = declaration.get_value_type()
                    if isinstance(value_type, FactValueType):
                        return value_type
        return self._declared_collection_field_type(name)

    def _declared_collection_field_type(self, name: str) -> Optional[FactValueType]:
        if self.__node_set is None or not isinstance(name, str):
            return None

        candidate = name.strip()
        field_candidates = {candidate}
        if "." in candidate:
            field_candidates.add(candidate.split(".", 1)[1].strip())

        for type_metadata in self.__node_set.get_type_dictionary().values():
            fields = type_metadata.get("fields", {})
            for field_name, field_type in fields.items():
                if (
                    field_name in field_candidates
                    or candidate.endswith(f"  {field_name}")
                    or candidate.endswith(f".{field_name}")
                ) and isinstance(field_type, FactValueType):
                    return field_type

        for collection_metadata in self.__node_set.get_collection_dictionary().values():
            for field_name, field_type in collection_metadata.get("fields", {}).items():
                if (
                    field_name in field_candidates
                    or candidate.endswith(f"  {field_name}")
                    or candidate.endswith(f".{field_name}")
                ) and isinstance(field_type, FactValueType):
                    return field_type
        return None

    def _infer_question_value_type(
        self,
        node: Node,
        question_name: str,
    ) -> FactValueType:
        """
        Protected Helper: Infers the expected answer type for a question key.
        """
        declared_type = self._declared_value_type(question_name)
        if declared_type is not None:
            return declared_type

        line_type = node.get_line_type()
        node_name = node.get_node_name()
        if question_name == node_name:
            return self._infer_node_value_type(node)

        if line_type == LineType.COMPARISON and hasattr(node, "get_rhs"):
            rhs = node.get_rhs()
            if hasattr(rhs, "get_value"):
                rhs_value = rhs.get_value()
                if isinstance(rhs_value, str):
                    rhs_declared_type = self._declared_value_type(rhs_value)
                    if rhs_declared_type is not None:
                        return rhs_declared_type
            if hasattr(rhs, "get_value_type"):
                rhs_type = rhs.get_value_type()
                if isinstance(rhs_type, FactValueType) and rhs_type != FactValueType.UNKNOWN:
                    return rhs_type

        if line_type == LineType.VALUE_CONCLUSION and hasattr(node, "get_is_plain_statement"):
            if node.get_is_plain_statement():
                return FactValueType.BOOLEAN

        fact_value = node.get_fact_value()
        if hasattr(fact_value, "get_value_type"):
            value_type = fact_value.get_value_type()
            if isinstance(value_type, FactValueType):
                return value_type
        return FactValueType.UNKNOWN

    def _infer_node_value_type(self, node: Node) -> FactValueType:
        """
        Protected Helper: Infers the result type produced by a node.
        """
        line_type = node.get_line_type()
        if line_type == LineType.COMPARISON:
            return FactValueType.BOOLEAN
        if line_type == LineType.VALUE_CONCLUSION and hasattr(node, "get_is_plain_statement"):
            if node.get_is_plain_statement():
                return FactValueType.BOOLEAN

        fact_value = node.get_fact_value()
        if hasattr(fact_value, "get_value_type"):
            value_type = fact_value.get_value_type()
            if isinstance(value_type, FactValueType):
                return value_type
        return FactValueType.UNKNOWN

    def get_next_question_with_goal_name(self, goal_name: str) -> Optional[Node]:
        """
        Public API: Gets next question node with specific goal name.
        
        Args:
            goal_name: Name of the goal rule
            
        Returns:
            Node to be asked or None
        """
        assessment = self.__asses.get_assessment(goal_name)
        return self.get_next_question(assessment)

    def get_next_question(self, ass: Assessment) -> Optional[Node]:
        """
        Public API: Gets next question node using backward chaining.
        
        Args:
            ass: Assessment to process
            
        Returns:
            Node to be asked or None
        """
        if self.__node_set is None or ass.get_goal_node() is None:
            return None
            
        if ass.get_goal_node().get_node_name() not in self.__ast.get_inclusive_list():
            self.__ast.get_inclusive_list().append(ass.get_goal_node().get_node_name())

        if self._assessment_has_converged(ass):
            ass.set_node_to_be_asked(None)
            ass.set_aux_node_to_be_asked(None)
            return None

        if (self.__ast.get_working_memory().get(ass.get_goal_node().get_node_name()) is None) or \
                (not self.__ast.all_mandatory_node_determined()):
            for index, target_node in self._question_flow_scan_nodes(ass):
                node_name = target_node.get_node_name()
                
                if index != ass.get_goal_node_index():
                    self._process_parent_dependencies(target_node, ass)
                
                if self._should_ask_node(target_node, ass, index):
                    node_to_be_asked = ass.get_node_to_be_asked()
                    if node_to_be_asked is not None and node_to_be_asked.get_line_type() == LineType.ITERATE:
                        return ass.get_aux_node_to_be_asked() or node_to_be_asked
                    return node_to_be_asked
                elif self._has_children_to_process(target_node, ass):
                    self._add_child_rule_into_inclusive_list(target_node)

        return self._active_askable_node(ass)

    def _assessment_has_converged(self, ass: Assessment) -> bool:
        goal_name = ass.get_goal_node().get_node_name()
        return (
            self._goal_fact_is_satisfied(self.__ast.get_working_memory().get(goal_name))
            and self.__ast.all_mandatory_node_determined()
        )

    @staticmethod
    def _goal_fact_is_satisfied(fact_value: Optional[FactValue]) -> bool:
        if fact_value is None:
            return False
        value = fact_value.get_value()
        if value is None:
            return False
        return True

    def _active_askable_node(self, ass: Assessment) -> Optional[Node]:
        active_node = ass.get_node_to_be_asked()
        if active_node is None:
            ass.set_aux_node_to_be_asked(None)
            return None

        if active_node.get_line_type() == LineType.ITERATE:
            if self._node_answer_is_known(active_node):
                ass.set_node_to_be_asked(None)
                ass.set_aux_node_to_be_asked(None)
                return None
            if self._node_is_deferred(active_node):
                ass.set_node_to_be_asked(None)
                ass.set_aux_node_to_be_asked(None)
                return None

            aux_node = ass.get_aux_node_to_be_asked()
            if aux_node is None or self._node_answer_is_known(aux_node):
                ass.set_aux_node_to_be_asked(None)
                return None
            if self._node_is_deferred(aux_node):
                ass.set_aux_node_to_be_asked(None)
                return None
            return aux_node

        if self._node_answer_is_known(active_node):
            ass.set_node_to_be_asked(None)
            ass.set_aux_node_to_be_asked(None)
            return None
        if self._node_is_deferred(active_node):
            ass.set_node_to_be_asked(None)
            ass.set_aux_node_to_be_asked(None)
            return None

        return active_node

    def _node_answer_is_known(self, node: Optional[Node]) -> bool:
        if node is None:
            return False

        working_memory = self.__ast.get_working_memory()
        return any(key in working_memory for key in self._answer_keys_for_node(node))

    def _answer_keys_for_node(self, node: Node) -> Set[str]:
        keys: Set[str] = set()
        for value in (
            node.get_node_name(),
            node.get_variable_name(),
            *self.get_questions_from_node_to_be_asked(node),
        ):
            if isinstance(value, str) and value:
                keys.add(value)
        return keys

    def _node_is_deferred(self, node: Optional[Node]) -> bool:
        if node is None or not self.__deferred_question_names:
            return False
        return any(key in self.__deferred_question_names for key in self._answer_keys_for_node(node))

    def _question_flow_scan_nodes(self, ass: Assessment) -> List[Tuple[int, Node]]:
        if self.__node_set is None or ass.get_goal_node() is None:
            return []

        sorted_nodes = list(self.__node_set.get_sorted_node_list())
        goal_name = ass.get_goal_node().get_node_name()
        target_names = self._target_reachable_node_names(goal_name)
        goal_index = max(ass.get_goal_node_index(), 0)

        ordered_indices: List[int] = []
        seen_indices: Set[int] = set()
        for index in range(goal_index, len(sorted_nodes)):
            if sorted_nodes[index].get_node_name() in target_names:
                ordered_indices.append(index)
                seen_indices.add(index)

        for index, node in enumerate(sorted_nodes):
            if index in seen_indices:
                continue
            if node.get_node_name() in target_names:
                ordered_indices.append(index)
                seen_indices.add(index)

        for index, _ in enumerate(sorted_nodes):
            if index not in seen_indices:
                ordered_indices.append(index)

        return [(index, sorted_nodes[index]) for index in ordered_indices]

    def _target_reachable_node_names(self, goal_name: str) -> Set[str]:
        if self.__dependency_graph is None:
            return {goal_name}

        visited: Set[str] = set()
        queue: Deque[str] = deque([goal_name])
        while queue:
            parent_name = queue.popleft()
            if parent_name in visited:
                continue
            visited.add(parent_name)

            for dep_type_int, children_tuple in self.__dependency_graph.get_child_groups(parent_name):
                for child_name in children_tuple:
                    queue.append(child_name)
        return visited

    def _mandatory_node_should_survive_pruning(self, node_name: str) -> bool:
        return (
            self.__ast.is_in_mandatory_list(node_name)
            and self._get_deterministic_fact(node_name) is None
        )

    def _retain_mandatory_node_for_question_flow(
        self,
        node_name: str,
        *,
        parent_name: str,
        reason: str,
    ) -> None:
        self.__ast.add_item_to_mandatory_list(node_name)
        removed_from: List[str] = []
        if node_name in self.__pruned_question_flow_nodes:
            self.__pruned_question_flow_nodes.remove(node_name)
            removed_from.append("pruned_question_flow_nodes")
        if (
            node_name not in self.__ast.get_inclusive_list()
            and node_name not in self.__ast.get_exclusive_list()
        ):
            self.__ast.get_inclusive_list().append(node_name)
            removed_from.append("not_in_inclusive_list")

        self._record_question_flow_event(
            node_name,
            parent_name=parent_name,
            action="retained",
            reason=reason,
            removed_from=removed_from,
        )

    def _ordered_answer_keys_for_node(self, node: Node) -> List[str]:
        keys: List[str] = []
        for value in (
            *self.get_questions_from_node_to_be_asked(node),
            node.get_variable_name(),
            node.get_node_name(),
        ):
            if isinstance(value, str) and value and value not in keys:
                keys.append(value)
        return keys

    def _ontology_default_fact_value_for_node(
        self,
        node: Node,
    ) -> Optional[FactValue]:
        selected = self._select_ontology_auto_answer(node, record_abstain=False)
        if selected is None:
            return None
        return selected[1]

    def _try_ontology_auto_answer(
        self,
        target_node: Node,
        ass: Assessment,
    ) -> bool:
        selected = self._select_ontology_auto_answer(target_node, record_abstain=True)
        if selected is None:
            return False

        question_name, fact_value, suggestion = selected
        self.__ast.set_fact(question_name, fact_value, source=FactSource.ASSERTED)
        self.__ast.add_item_to_summary_list(question_name)
        self._materialize_ontology_derivations(question_name, fact_value)
        self._handle_node_evaluation(target_node, fact_value)
        self._propagate_inferred_truth_from(target_node.get_node_name())
        if self.__node_set is not None:
            self._back_propagating(
                self.__node_set.find_node_index(target_node.get_node_name())
            )
        ass.set_node_to_be_asked(None)
        ass.set_aux_node_to_be_asked(None)
        self._record_ontology_auto_answer_event(
            target_node,
            question_name,
            "auto_answered",
            suggestion=suggestion,
            fact_value=fact_value,
        )
        return True

    def _select_ontology_auto_answer(
        self,
        node: Node,
        *,
        record_abstain: bool,
    ) -> Optional[Tuple[str, FactValue, Dict[str, Any]]]:
        if not (
            self.__feature_flags.ontology_advisory_enabled
            and self.__feature_flags.ontology_auto_answer
        ):
            return None

        for fact_name in self._ordered_answer_keys_for_node(node):
            sources = self.__ast.get_fact_sources(fact_name)
            if FactSource.ASSERTED in sources:
                if record_abstain:
                    self._record_ontology_auto_answer_event(
                        node,
                        fact_name,
                        "abstained",
                        reason="asserted_fact_exists",
                    )
                return None
            if sources:
                if record_abstain:
                    self._record_ontology_auto_answer_event(
                        node,
                        fact_name,
                        "abstained",
                        reason="deterministic_fact_exists",
                    )
                return None

            suggestions = self.__ontology_value_suggestions.get(fact_name, [])
            if not suggestions:
                continue

            available = [
                item for item in suggestions
                if item.get("status", "available") == "available"
                and item.get("autoAnswerEligible", True) is True
                and item.get("suggestedValue") is not None
            ]
            if len(available) != 1:
                if record_abstain:
                    self._record_ontology_auto_answer_event(
                        node,
                        fact_name,
                        "abstained",
                        reason="ambiguous_or_contradictory_ontology_default",
                        suggestion=suggestions[0] if suggestions else None,
                    )
                return None

            suggestion = dict(available[0])
            if not self._ontology_snapshot_matches(suggestion):
                if record_abstain:
                    self._record_ontology_auto_answer_event(
                        node,
                        fact_name,
                        "abstained",
                        reason="stale_or_unversioned_ontology_snapshot",
                        suggestion=suggestion,
                    )
                return None

            confidence = _safe_float(suggestion.get("confidence"), 0.0)
            threshold = self.__feature_flags.ontology_auto_answer_confidence_threshold
            if confidence < threshold:
                if record_abstain:
                    self._record_ontology_auto_answer_event(
                        node,
                        fact_name,
                        "abstained",
                        reason="below_confidence_threshold",
                        suggestion=suggestion,
                    )
                return None

            fact_value = self._create_fact_value(
                suggestion["suggestedValue"],
                self._infer_question_value_type(node, fact_name),
            )
            if fact_value is None:
                if record_abstain:
                    self._record_ontology_auto_answer_event(
                        node,
                        fact_name,
                        "abstained",
                        reason="unparseable_default_value",
                        suggestion=suggestion,
                    )
                return None
            return fact_name, fact_value, suggestion

        return None

    def _ontology_snapshot_matches(self, suggestion: Dict[str, Any]) -> bool:
        candidate_hash = suggestion.get("ontologySnapshotHash")
        return bool(
            candidate_hash
            and self.__ontology_snapshot_hash
            and candidate_hash == self.__ontology_snapshot_hash
        )

    def _record_ontology_auto_answer_event(
        self,
        node: Node,
        fact_name: str,
        status: str,
        *,
        reason: Optional[str] = None,
        suggestion: Optional[Dict[str, Any]] = None,
        fact_value: Optional[FactValue] = None,
    ) -> None:
        event: Dict[str, Any] = {
            "nodeName": node.get_node_name(),
            "factName": fact_name,
            "status": status,
            "reason": reason,
            "sourceLabel": FactSource.SEMANTIC.value,
            "autoAnswered": status == "auto_answered",
            "altersDeterministicOutcome": status == "auto_answered",
        }
        if suggestion is not None:
            event.update({
                "relationship": suggestion.get("relationship"),
                "confidence": suggestion.get("confidence"),
                "ontologySnapshotRef": suggestion.get("ontologySnapshotRef"),
                "ontologySnapshotHash": suggestion.get("ontologySnapshotHash"),
                "basis": suggestion.get("basis"),
            })
        if fact_value is not None:
            event.update({
                "suggestedValue": fact_value.get_value(),
                "valueType": fact_value.get_value_type().value,
                "factSource": FactSource.ASSERTED.value,
            })
        self.__ontology_auto_answer_trace.append(event)

    def _process_parent_dependencies(self, target_node: Node, ass: Assessment) -> None:
        """
        Protected Helper: Processes parent dependencies for a node.
        
        Args:
            target_node: Target node to process
            ass: Current assessment
        """
        if self.__node_set is None or self.__dependency_graph is None:
            return
        node_name = target_node.get_node_name()
        parent_names: Set[str] = self.__dependency_graph.get_parent_edges(node_name)
        if len(parent_names) > 0:
            for parent_name in parent_names:
                dep_type = self.__dependency_graph.get_dependency_type(parent_name, node_name)
                parent_in_question_flow = self.__ast.is_in_inclusive_list(parent_name)
                if dep_type != -1 \
                        and dep_type & DependencyType.get_mandatory() == DependencyType.get_mandatory() \
                        and parent_in_question_flow \
                        and not self.__ast.is_in_inclusive_list(node_name) \
                        and node_name not in self.__pruned_question_flow_nodes \
                        and not self._is_iterate_line_child(node_name):
                    self.__ast.add_item_to_mandatory_list(node_name)

    def _should_ask_node(self, target_node: Node, ass: Assessment, index: int) -> bool:
        """
        Protected Helper: Determines if a node should be asked.
        
        Args:
            target_node: Target node to evaluate
            ass: Current assessment
            index: Node index in sorted list
            
        Returns:
            True if node should be asked
        """
        node_name = target_node.get_node_name()
        if node_name not in self.__ast.get_inclusive_list():
            return False
        if self._node_is_deferred(target_node):
            return False
        if node_name in self.__pruned_question_flow_nodes:
            return False
        if self._prune_resolved_false_parent_branch(node_name):
            return False
        if self._has_pending_branch_discriminator(node_name):
            return False
        if node_name != ass.get_goal_node().get_node_name() \
                and target_node.get_line_type() == LineType.ITERATE \
                and node_name not in self.__ast.get_working_memory().keys():
            return self._handle_iterate_node(target_node, ass, index)
        elif not self._has_children(node_name) \
                and not self._try_ontology_auto_answer(target_node, ass) \
                and not self._can_evaluate(target_node):
            selected_node = self._select_question_strategy_frontier_candidate(
                target_node
            )
            if selected_node is None:
                return False
            ass.set_node_to_be_asked(selected_node)
            _logger.info("index Of Rule To Be Asked : " + str(index))
            return True
        return False

    def _select_question_strategy_frontier_candidate(
        self,
        target_node: Node,
    ) -> Optional[Node]:
        if self.__question_strategy is None:
            if self._question_strategy_allows_ask(
                target_node,
                has_children=False,
            ):
                return target_node
            return None

        candidates = self._askable_frontier_candidates()
        if not candidates:
            candidates = [target_node]
        return self.__question_strategy.select_next(
            candidates,
            self.__ast.get_working_memory(),
            has_children_by_name={
                node.get_node_name(): False for node in candidates
            },
        )

    def _askable_frontier_candidates(self) -> List[Node]:
        if self.__node_set is None:
            return []

        candidates: List[Node] = []
        for node in self.__node_set.get_sorted_node_list():
            node_name = node.get_node_name()
            if node.get_line_type() == LineType.ITERATE:
                continue
            if node_name not in self.__ast.get_inclusive_list():
                continue
            if self._node_is_deferred(node):
                continue
            if node_name in self.__pruned_question_flow_nodes:
                continue
            if self._has_children(node_name):
                continue
            if self._has_pending_branch_discriminator(node_name):
                continue
            if self._can_evaluate_without_mutation(node):
                continue
            if self.__question_resolver.find_next_question_node(
                node,
                self.__ast.get_working_memory(),
                has_children=False,
            ) is None:
                continue
            candidates.append(node)
        return candidates

    def _can_evaluate_without_mutation(self, target_node: Node) -> bool:
        line_type = target_node.get_line_type()
        working_memory = self.__ast.get_working_memory()

        if LineType.VALUE_CONCLUSION == line_type:
            value_conclusion: ValueConclusionLine = target_node
            if (
                value_conclusion.get_is_plain_statement()
                and value_conclusion.get_variable_name() in working_memory
            ):
                return True
            return (
                len(
                    list(
                        filter(
                            lambda token_string: token_string == "IS IN LIST: ",
                            value_conclusion.get_tokens().get_tokens_list(),
                        )
                    )
                ) > 0
                and str(value_conclusion.get_fact_value().get_value()) in working_memory
                and value_conclusion.get_variable_name() in working_memory
            )

        if LineType.COMPARISON == line_type:
            comparison: ComparisonLine = target_node
            node_rhs_value: FactValue = comparison.get_rhs()
            if FactValueType.STRING != node_rhs_value.get_value_type():
                return comparison.get_lhs() in working_memory
            return (
                comparison.get_lhs() in working_memory
                and str(comparison.get_rhs().get_value()) in working_memory
            )

        return False

    def _question_strategy_allows_ask(
        self,
        target_node: Node,
        *,
        has_children: bool,
    ) -> bool:
        if self.__question_strategy is not None:
            return self.__question_strategy.should_ask(
                target_node,
                self.__ast.get_working_memory(),
                has_children=has_children,
            )
        return self.__question_resolver.find_next_question_node(
            target_node,
            self.__ast.get_working_memory(),
            has_children=has_children,
        ) is not None

    def _prune_resolved_false_parent_branch(
        self,
        node_name: str,
        visited: Optional[Set[str]] = None,
    ) -> bool:
        if self.__node_set is None or self.__dependency_graph is None:
            return False

        visited = visited or set()
        if node_name in visited:
            return node_name in self.__pruned_question_flow_nodes
        visited.add(node_name)

        node_dict = self.__node_set.get_node_dictionary()
        for parent_name in self.__dependency_graph.get_parent_edges(node_name):
            if parent_name in self.__pruned_question_flow_nodes:
                self._prune_question_flow_subtree(
                    node_name,
                    parent_name=parent_name,
                    reason="parent_branch_false",
                )
                if node_name in self.__pruned_question_flow_nodes:
                    return True
                continue

            parent_node = node_dict.get(parent_name)
            parent_fact = self._get_deterministic_fact(parent_name)
            if (
                parent_fact is None
                and parent_node is not None
                and parent_name in self.__ast.get_inclusive_list()
                and self.__dependency_graph.get_children_flat(parent_name)
                and self._can_prune_false_parent_question_flow(parent_name)
            ):
                self._can_determine(parent_node, parent_node.get_line_type())
                parent_fact = self._get_deterministic_fact(parent_name)

            if (
                parent_fact is not None
                and parent_fact.get_value() is False
                and self._can_prune_false_parent_question_flow(parent_name)
            ):
                self._prune_children_skipped_by_false_parent(parent_name)
                if node_name in self.__pruned_question_flow_nodes:
                    return True

            if self._prune_resolved_false_parent_branch(parent_name, visited):
                if node_name in self.__pruned_question_flow_nodes:
                    return True

        return node_name in self.__pruned_question_flow_nodes

    def _has_pending_branch_discriminator(
        self,
        node_name: str,
    ) -> bool:
        if self.__node_set is None or self.__dependency_graph is None:
            return False

        node_dict = self.__node_set.get_node_dictionary()
        target_node = node_dict.get(node_name)
        target_question = self._question_name_for_node(target_node) if target_node is not None else None

        for branch_name in self._or_branch_ancestors(node_name):
            branch_fact = self._get_deterministic_fact(branch_name)
            if branch_fact is not None:
                continue

            for child_name in self.__dependency_graph.get_children_flat(branch_name):
                if child_name in self.__pruned_question_flow_nodes:
                    continue
                child_node = node_dict.get(child_name)
                if child_node is None or child_node.get_line_type() != LineType.COMPARISON:
                    continue

                question_name = self._question_name_for_node(child_node)
                if not question_name or self._node_answer_is_known(child_node):
                    continue
                if child_name == node_name or question_name == target_question:
                    continue
                return True

        return False

    def _or_branch_ancestors(self, node_name: str) -> Set[str]:
        if self.__dependency_graph is None:
            return set()

        branch_names: Set[str] = set()
        visited: Set[str] = set()
        queue: Deque[str] = deque(self.__dependency_graph.get_parent_edges(node_name))
        while queue:
            current_name = queue.popleft()
            if current_name in visited:
                continue
            visited.add(current_name)

            parent_names = self.__dependency_graph.get_parent_edges(current_name)
            for parent_name in parent_names:
                dep_type = self.__dependency_graph.get_dependency_type(parent_name, current_name)
                if dep_type != -1 and dep_type & DependencyType.get_or():
                    branch_names.add(current_name)
                queue.append(parent_name)

        return branch_names

    def _handle_iterate_node(self, target_node: Node, ass: Assessment, index: int) -> bool:
        """
        Protected Helper: Selects the next sub-question for an iterate node.

        The assessment keeps the iterate line as the active node so
        feed_answer_to_node() can route through iterate-specific answer
        handling, while the returned aux node is the concrete question shown to
        the API caller.
        """
        if self.__node_set is None:
            return False

        get_iterate_next_question = getattr(target_node, "get_iterate_next_question", None)
        if get_iterate_next_question is None:
            return False

        next_question_node = get_iterate_next_question(self.__node_set, self.__ast)
        if next_question_node is None:
            can_be_self_evaluated = getattr(target_node, "can_be_self_evaluated", None)
            if callable(can_be_self_evaluated) and can_be_self_evaluated(self.__ast.get_working_memory()):
                fact_value = target_node.self_evaluate(self.__ast.get_working_memory())
                if fact_value is not None:
                    self.__ast.set_fact(
                        target_node.get_node_name(),
                        fact_value,
                        source=FactSource.INFERRED,
                    )
                    self.__ast.add_item_to_summary_list(target_node.get_node_name())
            return False

        ass.set_node_to_be_asked(target_node)
        ass.set_aux_node_to_be_asked(next_question_node)
        _logger.info("index Of Rule To Be Asked : " + str(index))
        return True

    def _has_children_to_process(self, target_node: Node, ass: Assessment) -> bool:
        """
        Protected Helper: Checks if node has children to process.
        
        Args:
            target_node: Target node to evaluate
            ass: Current assessment
            
        Returns:
            True if children need processing
        """
        node_name = target_node.get_node_name()
        return node_name in self.__ast.get_inclusive_list() \
                and self._has_children(node_name) \
                and target_node.get_variable_name() not in self.__ast.get_working_memory().keys() \
                and node_name not in self.__ast.get_working_memory().keys()

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Fact Management)
    # -------------------------------------------------------------------------
    def add_node_fact(self, node_variable_name: str, fv: FactValue) -> None:
        """
        Public API: Adds a node fact before inference process.
        
        Args:
            node_variable_name: Variable name of the node
            fv: FactValue to store
        """
        if self.__node_set is None:
            return
        for each_node in self.__node_set.get_node_dictionary().values():
            if (each_node.get_variable_name() == node_variable_name) or \
                    (str(each_node.get_fact_value().get_value()) == node_variable_name):
                self.__node_fact_list.append(each_node)
        self.__ast.set_fact(node_variable_name, fv, source=FactSource.ASSERTED)

    def edit_answer(self, question_name: str) -> None:
        """
        Public API: Rewinds assessment state from an edited answer.

        The edited answer and every later summary fact are removed across all
        fact layers so callers can replay the rule path from that point.
        """
        if not question_name or not self._is_deterministic_fact(question_name):
            raise ValueError(f"Answer '{question_name}' has not been answered")

        summary_list = list(self.__ast.get_summary_list())
        if question_name in summary_list:
            edit_index = summary_list.index(question_name)
            stale_fact_names = summary_list[edit_index:]
            retained_summary = summary_list[:edit_index]
        else:
            stale_fact_names = [question_name]
            retained_summary = [
                fact_name for fact_name in summary_list if fact_name != question_name
            ]

        for fact_name in stale_fact_names:
            self.__ast.remove_fact(fact_name)

        self.__ast.set_summary_list(retained_summary)
        self.__ast.set_inclusive_list([])
        self.__ast.set_exclusive_list([])
        self.__ast.set_mandatory_list([])
        self.__branch_prune_trace.clear()
        self.__pruned_question_flow_nodes.clear()
        self.__ontology_materialization_trace.clear()
        self.__ontology_derived_facts.clear()

        assessments = set(self.__asses.get_assessments_dict().values())
        assessments.add(self.__ass)
        for assessment in assessments:
            assessment.set_node_to_be_asked(None)
            assessment.set_aux_node_to_be_asked(None)

    def feed_answer_to_node(
        self,
        target_node: Node,
        question_name: str,
        node_value: Any,
        node_value_type: FactValueType,
        ass: Assessment,
    ) -> None:
        """
        Public API: Feeds an answer to a node and propagates changes.
        
        Args:
            target_node: Target node
            question_name: Name of the question
            node_value: Value from user
            node_value_type: Type of the value
            ass: Current assessment
        """
        fact_value: Optional[FactValue] = self._create_fact_value(node_value, node_value_type)

        if fact_value is not None and LineType.ITERATE != ass.get_node_to_be_asked().get_line_type():
            self.__ast.set_fact(question_name, fact_value)
            self.__ast.add_item_to_summary_list(question_name)
            self._materialize_ontology_derivations(question_name, fact_value)
            self._handle_node_evaluation(target_node, fact_value)
            self._propagate_inferred_truth_from(target_node.get_node_name())
            self._back_propagating(self.__node_set.find_node_index(target_node.get_node_name()))
            ass.set_node_to_be_asked(None)
            ass.set_aux_node_to_be_asked(None)
        elif LineType.ITERATE == ass.get_node_to_be_asked().get_line_type():
            self._handle_iterate_answer(target_node, ass, question_name, node_value, node_value_type)

    def _materialize_ontology_derivations(
        self,
        source_fact_name: str,
        fact_value: FactValue,
    ) -> None:
        if not self.__feature_flags.ontology_reasoning:
            return
        if self.__ontology_reasoner is None or self.__ontology_index is None:
            return

        result = self.__ontology_reasoner.materialize(
            source_fact_name,
            fact_value,
            self.__ontology_index,
            fact_store=self.__ast.get_fact_store(),
        )
        self.__ontology_materialization_trace.extend(dict(item) for item in result.trace)

        for derived in result.derived_facts:
            if FactSource.ASSERTED in self.__ast.get_fact_sources(derived.fact_name):
                continue
            self.__ast.set_fact(
                derived.fact_name,
                derived.fact_value,
                source=FactSource.INFERRED,
            )
            self.__ast.add_item_to_summary_list(derived.fact_name)
            if derived.fact_name not in self.__ontology_derived_facts:
                self.__ontology_derived_facts.append(derived.fact_name)
            self._propagate_inferred_truth_from(derived.fact_name)

    def _create_fact_value(self, node_value: Any, node_value_type: FactValueType) -> Optional[FactValue]:
        """
        Protected Helper: Creates FactValue from user input.
        SECURITY FIX: Removed eval() for boolean parsing.
        
        Args:
            node_value: Value from user
            node_value_type: Type of the value
            
        Returns:
            FactValue or None
        """
        fact_value: Optional[FactValue] = None
        if FactValueType.BOOLEAN == node_value_type:
            if isinstance(node_value, bool):
                fact_value = FactValue(node_value, FactValueType.BOOLEAN)
            elif isinstance(node_value, str):
                # SECURITY FIX: Safe boolean parsing without eval()
                if node_value.lower() == 'true':
                    fact_value = FactValue(True, FactValueType.BOOLEAN)
                elif node_value.lower() == 'false':
                    fact_value = FactValue(False, FactValueType.BOOLEAN)
        elif FactValueType.DATE == node_value_type:
            fact_value = FactValue(node_value, FactValueType.DATE)
        elif FactValueType.DOUBLE == node_value_type:
            fact_value = FactValue(float(str(node_value)))
        elif FactValueType.INTEGER == node_value_type:
            fact_value = FactValue(int(node_value))
        elif FactValueType.STRING == node_value_type:
            fact_value = FactValue(str(node_value))
        elif FactValueType.DEFI_STRING == node_value_type:
            fact_value = FactValue(str(node_value), FactValueType.DEFI_STRING)
        elif node_value_type == FactValueType.LIST:
            value = node_value if isinstance(node_value, list) else [node_value]
            fact_value = FactValue(value, FactValueType.LIST)
        elif node_value_type in [FactValueType.HASH, FactValueType.URL, FactValueType.GUID]:
            fact_value = FactValue(node_value, node_value_type)
        return fact_value

    def _handle_node_evaluation(self, target_node: Node, fact_value: FactValue) -> None:
        """
        Protected Helper: Handles node self-evaluation after answer.
        
        Args:
            target_node: Target node
            fact_value: FactValue to store
        """
        if LineType.VALUE_CONCLUSION == target_node.get_line_type() \
                and not target_node.get_is_plain_statement():
            self_eval_fact_value: FactValue = target_node.self_evaluate(self.__ast.get_working_memory())
            self.__ast.set_fact(target_node.get_node_name(), self_eval_fact_value)
            self.__ast.add_item_to_summary_list(target_node.get_node_name())
        elif LineType.COMPARISON == target_node.get_line_type():
            rhs_value: FactValue = target_node.get_rhs()
            if (FactValueType.STRING == rhs_value.get_value_type()
                    and str(rhs_value.get_value()) in self.__ast.get_working_memory().keys()) \
                    or FactValueType.STRING != rhs_value.get_value_type():
                self_eval_fact_value: FactValue = target_node.self_evaluate(self.__ast.get_working_memory())
                self.__ast.set_fact(target_node.get_node_name(), self_eval_fact_value)
                self.__ast.add_item_to_summary_list(target_node.get_node_name())

    def _handle_iterate_answer(
        self,
        target_node: Node,
        ass: Assessment,
        question_name: str,
        node_value: Any,
        node_value_type: FactValueType,
    ) -> None:
        """
        Protected Helper: Handles answer for iterate line nodes.

        Phase 1 WS-3 integration: after the legacy iterate_feed_answers() call,
        if the iterate node can be self-evaluated, the conclusion is tagged
        FactSource.INFERRED instead of the default ASSERTED.

        Args:
            target_node: Target node
            ass: Current assessment
            question_name: Name of the question
            node_value: Value from user
            node_value_type: Type of the value
        """
        iterate_node = ass.get_node_to_be_asked()
        target_node = ass.get_aux_node_to_be_asked()
        iterate_node.iterate_feed_answers(
            target_node, question_name, node_value, node_value_type,
            self.__node_set, self.__ast, ass,
            feature_flags=self.__feature_flags,
        )
        ass.set_aux_node_to_be_asked(None)
        if iterate_node.can_be_self_evaluated(self.__ast.get_working_memory()):
            # Tag the iterate conclusion as INFERRED (derived by the rule engine)
            eval_result = iterate_node.self_evaluate(self.__ast.get_working_memory())
            self.__ast.set_fact(
                iterate_node.get_node_name(),
                eval_result,
                source=FactSource.INFERRED,
            )
            self.__ast.add_item_to_summary_list(iterate_node.get_node_name())
            self._propagate_inferred_truth_from(iterate_node.get_node_name())
            self._back_propagating(self.__node_set.find_node_index(iterate_node.get_node_name()))
            ass.set_node_to_be_asked(None)
            ass.set_aux_node_to_be_asked(None)

    def _propagate_inferred_truth_from(
        self,
        child_node_name: str,
        visited: Optional[Set[str]] = None,
    ) -> None:
        """
        Protected Helper: Propagates an inferred child truth value to parents.

        This is especially important for iterate conclusions, which are derived
        from a nested node set and then copied back into the parent engine.
        """
        if self.__dependency_graph is None:
            return
        visited = visited or set()
        if child_node_name in visited:
            return
        visited.add(child_node_name)

        for parent_name in self.__dependency_graph.get_parent_edges(child_node_name):
            if parent_name in visited:
                continue
            parent_value = self._compute_parent_truth_from_children(parent_name)
            if parent_value is None:
                continue
            self.__ast.set_fact(parent_name, parent_value, source=FactSource.INFERRED)
            self.__ast.add_item_to_summary_list(parent_name)
            if parent_value.get_value() is False:
                if self._can_prune_false_parent_question_flow(parent_name):
                    self._prune_children_skipped_by_false_parent(parent_name)
            else:
                self._prune_or_siblings_skipped_by_true_parent(parent_name)
            self._propagate_inferred_truth_from(parent_name, visited)

    def _compute_parent_truth_from_children(
        self,
        parent_name: str,
        visited: Optional[Set[str]] = None,
    ) -> Optional[FactValue]:
        if self.__dependency_graph is None:
            return None
        visited = visited or set()
        if parent_name in visited:
            return None
        visited.add(parent_name)
        group_results: List[bool] = []
        saw_and_group = False
        missing_required_group = False

        for dep_type_int, children_tuple in self.__dependency_graph.get_child_groups(parent_name):
            children = tuple(children_tuple)
            if not children:
                continue

            is_optional_dependency = (
                dep_type_int & DependencyType.get_optional()
                or dep_type_int & DependencyType.get_possible()
            )
            missing_child_count = 0
            child_values: List[bool] = []
            for child_name in children:
                child_value = self._dependency_child_truth(
                    dep_type_int,
                    child_name,
                    visited,
                )
                if child_value is None:
                    missing_child_count += 1
                    continue
                child_values.append(child_value)

            if dep_type_int & DependencyType.get_and():
                if (
                    any(value is False for value in child_values)
                    and self._can_short_circuit_false_and(parent_name)
                ):
                    group_value = False
                elif missing_child_count and not is_optional_dependency:
                    missing_required_group = True
                    continue
                elif missing_child_count == len(children) and is_optional_dependency:
                    continue
                else:
                    group_value = all(child_values)
                saw_and_group = True
            elif dep_type_int & DependencyType.get_or():
                if any(child_values):
                    group_value = True
                elif missing_child_count == 0:
                    group_value = False
                elif is_optional_dependency and not child_values:
                    continue
                else:
                    missing_required_group = True
                    continue
            else:
                if missing_child_count and not is_optional_dependency:
                    missing_required_group = True
                    continue
                if missing_child_count == len(children) and is_optional_dependency:
                    continue
                group_value = all(child_values)

            group_results.append(group_value)

        if not group_results:
            return None
        if saw_and_group:
            if (
                any(value is False for value in group_results)
                and self._can_short_circuit_false_and(parent_name)
            ):
                return FactValue(False, FactValueType.BOOLEAN)
            if missing_required_group:
                return None
            return FactValue(all(group_results), FactValueType.BOOLEAN)
        if any(group_results):
            return FactValue(True, FactValueType.BOOLEAN)
        if missing_required_group:
            return None
        return FactValue(any(group_results), FactValueType.BOOLEAN)

    def _dependency_child_truth(
        self,
        dep_type_int: int,
        child_name: str,
        visited: Optional[Set[str]] = None,
    ) -> Optional[bool]:
        self._evaluate_known_leaf_node(child_name)
        child_fact = self._get_deterministic_fact(child_name)
        has_children = (
            self.__dependency_graph is not None
            and bool(self.__dependency_graph.get_children_flat(child_name))
        )
        if (
            has_children
            and not self._is_comparison_node(child_name)
            and FactSource.ASSERTED not in self.__ast.get_fact_sources(child_name)
            and child_name not in (visited or set())
        ):
            child_value = self._compute_parent_truth_from_children(
                child_name,
                visited,
            )
            if child_value is not None:
                self.__ast.set_fact(child_name, child_value, source=FactSource.INFERRED)
                self.__ast.add_item_to_summary_list(child_name)
                if child_value.get_value() is False:
                    if self._can_prune_false_parent_question_flow(child_name):
                        self._prune_children_skipped_by_false_parent(child_name)
                else:
                    self._prune_or_siblings_skipped_by_true_parent(child_name)
                child_fact = self._get_deterministic_fact(child_name)

        if dep_type_int & DependencyType.get_known():
            if child_fact is None and not dep_type_int & DependencyType.get_not():
                if self._known_dependency_should_wait_for_input(child_name):
                    return None
                if self._or_branch_ancestors(child_name):
                    return None
                child_value = False
            else:
                child_value = child_fact is not None
        elif child_fact is None:
            return None
        else:
            child_value = bool(child_fact.get_value())

        if dep_type_int & DependencyType.get_not():
            child_value = not child_value
        return child_value

    def _known_dependency_should_wait_for_input(self, child_name: str) -> bool:
        if self.__node_set is None or not isinstance(child_name, str):
            return False

        try:
            input_dictionary = self.__node_set.get_input_dictionary()
        except Exception:
            return False

        if not isinstance(input_dictionary, dict):
            return False

        if child_name in input_dictionary:
            return True

        return any(
            child_name.endswith(f"  {declared_name}")
            for declared_name in input_dictionary.keys()
            if isinstance(declared_name, str) and declared_name
        )

    def _evaluate_known_leaf_node(self, node_name: str) -> None:
        if self.__node_set is None or self.__dependency_graph is None:
            return
        if self._get_deterministic_fact(node_name) is not None:
            return
        if self.__dependency_graph.get_children_flat(node_name):
            return

        node = self.__node_set.get_node_dictionary().get(node_name)
        if node is None:
            return

        line_type = node.get_line_type()
        if LineType.COMPARISON == line_type:
            if not self._can_evaluate_without_mutation(node):
                return
            fact_value = node.self_evaluate(self._get_deterministic_working_memory())
            if fact_value is None:
                return
            self.__ast.set_fact(node_name, fact_value, source=FactSource.INFERRED)
            self.__ast.add_item_to_summary_list(node_name)
            return

        if LineType.VALUE_CONCLUSION == line_type and self._can_evaluate(node):
            if self._get_deterministic_fact(node_name) is not None:
                self.__ast.add_item_to_summary_list(node_name)

    def _can_short_circuit_false_and(
        self,
        parent_name: str,
        visited: Optional[Set[str]] = None,
    ) -> bool:
        return self.__dependency_graph is not None

    def _can_prune_false_parent_question_flow(self, parent_name: str) -> bool:
        return self.__dependency_graph is not None

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Back Propagation)
    # -------------------------------------------------------------------------
    def _back_propagating(self, node_index: int) -> None:
        """
        Protected Helper: Propagates changes through the node set.
        
        Args:
            node_index: Index of the node that changed
        """
        if self.__node_set is None:
            return
        node_sorted_list: List[Node] = self.__node_set.get_sorted_node_list()
        sorted_list_size: int = len(node_sorted_list)
        for i in range(0, sorted_list_size):
            current_index = sorted_list_size - (i + 1)
            temp_node: Node = node_sorted_list[current_index]
            line_type: LineType = temp_node.get_line_type()
            self._process_node_dependencies(temp_node)
            self._evaluate_node_after_propagation(temp_node, line_type, node_index, current_index)

    def _process_node_dependencies(self, temp_node: Node) -> None:
        """
        Protected Helper: Processes dependencies for a node during propagation.
        
        Args:
            temp_node: Node to process
        """
        if self.__node_set is None or self.__dependency_graph is None:
            return
        node_name = temp_node.get_node_name()
        parent_names: Set[str] = self.__dependency_graph.get_parent_edges(node_name)
        if len(parent_names) > 0:
            for parent_name in parent_names:
                dep_type = self.__dependency_graph.get_dependency_type(parent_name, node_name)
                parent_in_question_flow = self.__ast.is_in_inclusive_list(parent_name)
                if dep_type != -1 \
                        and dep_type & DependencyType.get_mandatory() == DependencyType.get_mandatory() \
                        and parent_in_question_flow \
                        and not self.__ast.is_in_inclusive_list(node_name) \
                        and node_name not in self.__pruned_question_flow_nodes \
                        and not self._is_iterate_line_child(node_name):
                    self.__ast.add_item_to_mandatory_list(node_name)

    def _evaluate_node_after_propagation(
        self,
        temp_node: Node,
        line_type: LineType,
        node_index: int,
        current_index: int,
    ) -> None:
        """
        Protected Helper: Evaluates a node after back propagation.
        
        Args:
            temp_node: Node to evaluate
            line_type: Type of the node line
            node_index: Original node index
            current_index: Current index in iteration
        """
        node_name = temp_node.get_node_name()
        if (
            node_name not in self.__ast.get_inclusive_list()
            and node_name not in self.__ast.get_mandatory_list()
        ):
            return
        if node_index < current_index:
            if self._has_children(node_name):
                if node_name not in self.__ast.get_working_memory().keys() \
                        and self._can_determine(temp_node, line_type):
                    if LineType.EXPR_CONCLUSION != line_type:
                        self.__ast.add_item_to_summary_list(node_name)
            else:
                self._evaluate_leaf_node(temp_node, line_type)
        else:
            if node_name in self.__ast.get_inclusive_list():
                if node_name not in self.__ast.get_working_memory().keys() \
                        and self._has_children(node_name) \
                        and self._can_determine(temp_node, line_type):
                    if LineType.EXPR_CONCLUSION != line_type:
                        self.__ast.add_item_to_summary_list(node_name)

    def _evaluate_leaf_node(self, temp_node: Node, line_type: LineType) -> None:
        """
        Protected Helper: Evaluates leaf nodes during propagation.
        
        Args:
            temp_node: Node to evaluate
            line_type: Type of the node line
        """
        if LineType.VALUE_CONCLUSION == line_type \
                and not temp_node.get_is_plain_statement() \
                and temp_node.get_variable_name() in self.__ast.get_working_memory().keys():
            fact_value: FactValue = temp_node.self_evaluate(self.__ast.get_working_memory())
            self.__ast.set_fact(temp_node.get_node_name(), fact_value)
            self.__ast.add_item_to_summary_list(temp_node.get_node_name())
        elif LineType.COMPARISON == line_type \
                and temp_node.get_lhs() in self.__ast.get_working_memory().keys() \
                and ((FactValueType.STRING == temp_node.get_rhs().get_value_type() and str(
                    temp_node.get_rhs().get_value()) in self.__ast.get_working_memory().keys()) \
                or (FactValueType.STRING != temp_node.get_rhs().get_value_type())):
            fact_value: FactValue = temp_node.self_evaluate(self.__ast.get_working_memory())
            self.__ast.set_fact(temp_node.get_node_name(), fact_value)
            self.__ast.add_item_to_summary_list(temp_node.get_node_name())

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Utility)
    # -------------------------------------------------------------------------
    def get_list_of_variable_name_and_value_of_nodes(self) -> List[str]:
        """
        Public API: Extracts all variable names of nodes for display.
        
        Returns:
            List of variable names and values
        """
        variable_name_list: List[str] = []
        if self.__node_set is None or self.__dependency_graph is None:
            return variable_name_list
        for each_node in self.__node_set.get_node_dictionary().values():
            if len(self.__dependency_graph.get_children_flat(each_node.get_node_name())) == 0:
                variable_name_list.append(each_node.get_variable_name())
                node_fact_value_type: FactValueType = each_node.get_fact_value().get_value_type()
                if (node_fact_value_type == FactValueType.STRING) or (node_fact_value_type == FactValueType.TEXT):
                    variable_name_list.append(str(each_node.get_fact_value().get_value()))
        return variable_name_list

    def _has_children(self, node_name: str) -> bool:
        """
        Protected Helper: Checks if node has children.
        
        Args:
            node_name: Node name to check
            
        Returns:
            True if node has children
        """
        if self.__node_set is None or self.__dependency_graph is None:
            return False
        if node_name in self.__pruned_question_flow_nodes:
            return False
        children = self.__dependency_graph.get_children_flat(node_name)
        if len(children) != 0:
            if self._is_comparison_node(node_name):
                return False
            node_fact = self._get_deterministic_fact(node_name)
            if node_fact is not None and node_fact.get_value() is False:
                return True
            node_dict = self.__node_set.get_node_dictionary()
            node = node_dict.get(node_name)
            if (
                node is not None
                and node_name in self.__ast.get_inclusive_list()
                and node_name not in self.__ast.get_working_memory()
                and self._can_determine(node, node.get_line_type())
            ):
                return True
            for child_name in children:
                child_node = node_dict.get(child_name)
                if child_node is not None:
                    self._add_child_rule_into_inclusive_list(child_node)
            return True
        return False

    def _is_comparison_node(self, node_name: str) -> bool:
        if self.__node_set is None or not isinstance(node_name, str):
            return False
        node = self.__node_set.get_node_dictionary().get(node_name)
        return node is not None and node.get_line_type() == LineType.COMPARISON

    def _add_child_rule_into_inclusive_list(self, node: Node) -> None:
        """
        Protected Helper: Adds child rules to inclusive list.
        
        Args:
            node: Node whose children should be added
        """
        if self.__node_set is None or self.__dependency_graph is None:
            return
        node_fact = self._get_deterministic_fact(node.get_node_name())
        if node_fact is not None and node_fact.get_value() is False:
            return
        node_is_mandatory = self.__ast.is_in_mandatory_list(node.get_node_name())
        children = self.__dependency_graph.get_children_flat(node.get_node_name())
        for child_name in children:
            if child_name in self.__pruned_question_flow_nodes:
                if not node_is_mandatory:
                    continue
                self.__pruned_question_flow_nodes.remove(child_name)
                self._record_question_flow_event(
                    child_name,
                    parent_name=node.get_node_name(),
                    action="retained",
                    reason="mandatory_support_required",
                    removed_from=["pruned_question_flow_nodes"],
                )
            if child_name not in self.__ast.get_inclusive_list() \
                    and child_name not in self.__ast.get_exclusive_list():
                self.__ast.get_inclusive_list().append(child_name)
                if node_is_mandatory:
                    self._record_question_flow_event(
                        child_name,
                        parent_name=node.get_node_name(),
                        action="retained",
                        reason="mandatory_support_required",
                        removed_from=["not_in_inclusive_list"],
                    )

    def _is_iterate_line_child(self, node_name: str) -> bool:
        """
        Protected Helper: Checks if node is child of iterate line.
        
        Uses BFS walk-up via graph parent edges to check if any ancestor
        is an iterate node. More efficient than the previous walk-down
        approach which iterated all iterate nodes' descendants.
        
        Args:
            node_name: Node name to check
            
        Returns:
            True if node is iterate line child
        """
        if self.__node_set is None or self.__dependency_graph is None:
            return False
        node_dict = self.__node_set.get_node_dictionary()
        visited: Set[str] = set()
        queue: Deque[str] = deque([node_name])
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            for parent_name in self.__dependency_graph.get_parent_edges(current):
                parent_node = node_dict.get(parent_name)
                if parent_node is not None and parent_node.get_line_type() == LineType.ITERATE:
                    return True
                queue.append(parent_name)
        if node_name in self.__ast.get_mandatory_list():
            self.__ast.get_mandatory_list().remove(node_name)
        return False

    def _can_evaluate(self, target_node: Node) -> bool:
        """
        Protected Helper: Checks if node can be evaluated with current working memory.
        
        Args:
            target_node: Node to check
            
        Returns:
            True if node can be evaluated
        """
        can_be_evaluate = False
        line_type: LineType = target_node.get_line_type()

        if LineType.VALUE_CONCLUSION == line_type:
            value_conclusion: ValueConclusionLine = target_node
            if value_conclusion.get_is_plain_statement() and value_conclusion.get_variable_name() in self.__ast.get_working_memory():
                can_be_evaluate = True
            elif len(list(filter(lambda token_string: token_string == "IS IN LIST: ",
                                value_conclusion.get_tokens().get_tokens_list()))) > 0 \
                    and str(value_conclusion.get_fact_value().get_value()) in self.__ast.get_working_memory().keys() \
                    and value_conclusion.get_variable_name() in self.__ast.get_working_memory().keys():
                can_be_evaluate = True
                fact_value: FactValue = value_conclusion.self_evaluate(self.__ast.get_working_memory())
                self.__ast.set_fact(value_conclusion.get_node_name(), fact_value, value_conclusion)
        elif LineType.COMPARISON == line_type:
            comparison: ComparisonLine = target_node
            node_rhs_value: FactValue = comparison.get_rhs()
            if FactValueType.STRING != node_rhs_value.get_value_type() \
                    and comparison.get_lhs() in self.__ast.get_working_memory().keys():
                can_be_evaluate = True
                if comparison.get_node_name() not in self.__ast.get_working_memory().keys():
                    self.__ast.set_fact(comparison.get_node_name(), comparison.self_evaluate(self.__ast.get_working_memory()))
            elif FactValueType.STRING == node_rhs_value.get_value_type() \
                    and comparison.get_lhs() in self.__ast.get_working_memory().keys() \
                    and str(comparison.get_rhs().get_value()) in self.__ast.get_working_memory().keys():
                can_be_evaluate = True
                if comparison.get_node_name() not in self.__ast.get_working_memory().keys():
                    self.__ast.set_fact(comparison.get_node_name(), comparison.self_evaluate(self.__ast.get_working_memory()), comparison)
        return can_be_evaluate

    def _comparison_dependencies_ready(self, parent_name: str) -> bool:
        """
        Protected Helper: Checks whether comparison prerequisites are known.
        """
        if self.__dependency_graph is None:
            return False

        saw_ready_group = False
        for dep_type_int, children_tuple in self.__dependency_graph.get_child_groups(parent_name):
            children = tuple(children_tuple)
            if not children:
                continue

            is_optional_dependency = (
                dep_type_int & DependencyType.get_optional()
                or dep_type_int & DependencyType.get_possible()
            )
            if dep_type_int & DependencyType.get_known():
                evaluated = [True for _ in children]
            else:
                evaluated = [
                    self._has_deterministic_child_answer(child_name)
                    for child_name in children
                ]

            if dep_type_int & DependencyType.get_or():
                if any(evaluated):
                    saw_ready_group = True
                    continue
                if is_optional_dependency:
                    continue
                return False

            if all(evaluated):
                saw_ready_group = True
                continue
            if is_optional_dependency:
                continue
            return False

        return saw_ready_group

    def _can_determine(self, target_node: Node, line_type: LineType) -> bool:
        """
        Protected Helper: Checks if node can be determined with current facts.
        
        Args:
            target_node: Node to check
            line_type: Type of the node line
            
        Returns:
            True if node can be determined
        """
        if self.__node_set is None or self.__dependency_graph is None:
            return False

        node_name = target_node.get_node_name()
        child_groups = self.__dependency_graph.get_child_groups(node_name)
        if not child_groups:
            return False

        if LineType.VALUE_CONCLUSION == line_type:
            parent_value = self._compute_parent_truth_from_children(node_name)
            if parent_value is None:
                return False
            self.__ast.set_fact(node_name, parent_value, source=FactSource.INFERRED)
            if parent_value.get_value() is False:
                if self._can_prune_false_parent_question_flow(node_name):
                    self._prune_children_skipped_by_false_parent(node_name)
            else:
                self._prune_or_siblings_skipped_by_true_parent(node_name)
            return True

        if LineType.COMPARISON == line_type:
            if not self._comparison_dependencies_ready(node_name):
                return False
            fact_value = target_node.self_evaluate(self._get_deterministic_working_memory())
            if fact_value is None:
                return False
            self.__ast.set_fact(node_name, fact_value, source=FactSource.INFERRED)
            if fact_value.get_value() is False:
                if self._can_prune_false_parent_question_flow(node_name):
                    self._prune_children_skipped_by_false_parent(node_name)
            else:
                self._prune_or_siblings_skipped_by_true_parent(node_name)
            return True

        return False

    def _prune_or_siblings_skipped_by_true_parent(self, parent_name: str) -> None:
        if self.__dependency_graph is None:
            return

        or_children: List[Tuple[str, int]] = []
        seen_children: Set[str] = set()
        for dep_type_int, children_tuple in self.__dependency_graph.get_child_groups(parent_name):
            if not dep_type_int & DependencyType.get_or():
                continue
            for child_name in children_tuple:
                if child_name in seen_children:
                    continue
                seen_children.add(child_name)
                or_children.append((child_name, dep_type_int))

        if not or_children:
            return

        child_truth = {
            child_name: self._dependency_child_truth(dep_type_int, child_name)
            for child_name, dep_type_int in or_children
        }
        if not any(value is True for value in child_truth.values()):
            return

        for child_name, truth_value in child_truth.items():
            if truth_value is None:
                self._prune_question_flow_subtree(
                    child_name,
                    parent_name=parent_name,
                    reason=self._prune_reason_for_dependency(
                        parent_name,
                        child_name,
                        default_reason="or_branch_satisfied",
                    ),
                )

    def _prune_children_skipped_by_false_parent(
        self,
        parent_name: str,
        visited: Optional[Set[str]] = None,
    ) -> None:
        if self.__dependency_graph is None:
            return
        visited = visited or set()
        if parent_name in visited:
            return
        visited.add(parent_name)

        for child_name in self.__dependency_graph.get_children_flat(parent_name):
            if self._get_deterministic_fact(child_name) is not None:
                continue
            if self._mandatory_node_should_survive_pruning(child_name):
                self._retain_mandatory_node_for_question_flow(
                    child_name,
                    parent_name=parent_name,
                    reason="mandatory_dependency_survived_pruning",
                )
                continue
            if self._has_non_false_alternate_parent(child_name, parent_name):
                continue

            reason = self._prune_reason_for_dependency(
                parent_name,
                child_name,
                default_reason=self._false_parent_prune_reason(parent_name),
            )
            self._prune_question_flow_node(
                child_name,
                parent_name=parent_name,
                reason=reason,
            )

            for related_name in self._related_prunable_node_names(child_name):
                self._prune_question_flow_node(
                    related_name,
                    parent_name=child_name,
                    reason="branch_output_pruned",
                )
                self._prune_children_skipped_by_false_parent(related_name, visited)

            self._prune_children_skipped_by_false_parent(child_name, visited)

    def _prune_question_flow_subtree(
        self,
        node_name: str,
        *,
        parent_name: str,
        reason: str,
        visited: Optional[Set[str]] = None,
    ) -> None:
        if self.__dependency_graph is None:
            return
        visited = visited or set()
        if node_name in visited:
            return
        visited.add(node_name)

        if self._get_deterministic_fact(node_name) is not None:
            return
        if self._mandatory_node_should_survive_pruning(node_name):
            self._retain_mandatory_node_for_question_flow(
                node_name,
                parent_name=parent_name,
                reason="mandatory_dependency_survived_pruning",
            )
            return
        if self._has_non_false_alternate_parent(node_name, parent_name):
            return

        self._prune_question_flow_node(
            node_name,
            parent_name=parent_name,
            reason=reason,
        )
        for related_name in self._related_prunable_node_names(node_name):
            self._prune_question_flow_subtree(
                related_name,
                parent_name=node_name,
                reason="branch_output_pruned",
                visited=visited,
            )

        for child_name in self.__dependency_graph.get_children_flat(node_name):
            self._prune_question_flow_subtree(
                child_name,
                parent_name=node_name,
                reason=reason,
                visited=visited,
            )

    def _prune_question_flow_node(
        self,
        node_name: str,
        *,
        parent_name: str,
        reason: str,
    ) -> None:
        if self._mandatory_node_should_survive_pruning(node_name):
            self._retain_mandatory_node_for_question_flow(
                node_name,
                parent_name=parent_name,
                reason="mandatory_dependency_survived_pruning",
            )
            return

        self.__pruned_question_flow_nodes.add(node_name)
        removed_from = self._remove_from_question_flow(node_name)
        if removed_from:
            self._record_question_flow_event(
                node_name,
                parent_name=parent_name,
                action="pruned",
                reason=reason,
                removed_from=removed_from,
            )

    def _record_question_flow_event(
        self,
        node_name: str,
        *,
        parent_name: str,
        action: str,
        reason: str,
        removed_from: Optional[List[str]] = None,
    ) -> None:
        event = {
            "nodeName": node_name,
            "action": action,
            "reason": reason,
            "parentName": parent_name,
            "removedFrom": removed_from or [],
            "reversible": True,
        }
        if event not in self.__branch_prune_trace:
            self.__branch_prune_trace.append(event)
            _logger.info("question_flow_branch_pruned", **event)

    def _false_parent_prune_reason(self, parent_name: str) -> str:
        if self.__dependency_graph is None:
            return "and_parent_failed"

        for ancestor_name in self.__dependency_graph.get_parent_edges(parent_name):
            dep_type = self.__dependency_graph.get_dependency_type(
                ancestor_name,
                parent_name,
            )
            if dep_type != -1 and dep_type & DependencyType.get_or():
                return "parent_branch_false"

        if self._or_branch_ancestors(parent_name):
            return "parent_branch_false"
        return "and_parent_failed"

    def _prune_reason_for_dependency(
        self,
        parent_name: str,
        child_name: str,
        *,
        default_reason: str,
    ) -> str:
        if self.__dependency_graph is None:
            return default_reason

        dep_type = self.__dependency_graph.get_dependency_type(parent_name, child_name)
        if dep_type != -1 and dep_type & DependencyType.get_optional():
            return "optional_dependency_pruned"
        if dep_type != -1 and dep_type & DependencyType.get_possible():
            return "possible_dependency_pruned"
        return default_reason

    def _related_prunable_node_names(self, node_name: str) -> List[str]:
        if self.__node_set is None:
            return []

        node_dict = self.__node_set.get_node_dictionary()
        node = node_dict.get(node_name)
        if node is None:
            return []

        keys = {node_name}
        variable_name = node.get_variable_name()
        if isinstance(variable_name, str) and variable_name:
            keys.add(variable_name)

        related_names: List[str] = []
        for candidate_name, candidate in node_dict.items():
            if candidate_name == node_name:
                continue
            if self._get_deterministic_fact(candidate_name) is not None:
                continue
            if (
                candidate.get_node_name() in keys
                or candidate.get_variable_name() in keys
            ):
                related_names.append(candidate_name)
        return related_names

    def _has_non_false_alternate_parent(
        self,
        child_name: str,
        skipped_parent_name: str,
    ) -> bool:
        if self.__dependency_graph is None:
            return False

        for parent_name in self.__dependency_graph.get_parent_edges(child_name):
            if parent_name == skipped_parent_name:
                continue
            if parent_name in self.__pruned_question_flow_nodes:
                continue
            parent_fact = self._get_deterministic_fact(parent_name)
            if parent_fact is not None and parent_fact.get_value() is False:
                continue
            return True
        return False

    def _remove_from_question_flow(self, node_name: str) -> List[str]:
        removed_from: List[str] = []
        flow_lists = (
            ("inclusive_list", self.__ast.get_inclusive_list()),
            ("mandatory_list", self.__ast.get_mandatory_list()),
        )
        for list_name, values in flow_lists:
            if node_name in values:
                self.__ast.set_inclusive_list(
                    [value for value in values if value != node_name]
                ) if list_name == "inclusive_list" else self.__ast.set_mandatory_list(
                    [value for value in values if value != node_name]
                )
                removed_from.append(list_name)

        for assessment in set(self.__asses.get_assessments_dict().values()) | {self.__ass}:
            active_node = assessment.get_node_to_be_asked()
            aux_node = assessment.get_aux_node_to_be_asked()
            if active_node is not None and active_node.get_node_name() == node_name:
                assessment.set_node_to_be_asked(None)
                removed_from.append("active_node")
            if aux_node is not None and aux_node.get_node_name() == node_name:
                assessment.set_aux_node_to_be_asked(None)
                removed_from.append("aux_node")

        return removed_from

    def reset_working_memory_and_inclusive_list(self) -> None:
        """
        Public API: Resets working memory and inclusive list.
        
        Use when starting a new assessment with same conditions.
        """
        if len(self.__ast.get_inclusive_list()) > 0:
            self.__ast.get_inclusive_list().clear()
        self.__ast.set_working_memory({})
        self.__branch_prune_trace.clear()
        self.__pruned_question_flow_nodes.clear()
        self.__ontology_materialization_trace.clear()
        self.__ontology_derived_facts.clear()

    def get_default_goal_rule_question(self) -> Optional[str]:
        """
        Public API: Gets default goal rule question name.
        
        Returns:
            Goal rule name or None
        """
        if self.__node_set is None:
            return None
        return self.__node_set.get_default_goal_node().get_node_name()

    def get_assessment_goal_rule_question(self, ass: Assessment) -> Optional[str]:
        """
        Public API: Gets assessment goal rule question name.
        
        Args:
            ass: Assessment to query
            
        Returns:
            Goal rule name or None
        """
        return ass.get_goal_node().get_node_name() if ass.get_goal_node() else None

    def get_default_goal_rule_answer(self) -> Optional[FactValue]:
        """
        Public API: Gets default goal rule answer.
        
        Returns:
            FactValue or None
        """
        if self.__node_set is None:
            return None
        return self.__ast.get_working_memory().get(self.__node_set.get_default_goal_node().get_variable_name())

    def get_assessment_goal_rule_answer(self, ass: Assessment) -> Optional[FactValue]:
        """
        Public API: Gets assessment goal rule answer.
        
        Args:
            ass: Assessment to query
            
        Returns:
            FactValue or None
        """
        return self.__ast.get_working_memory().get(ass.get_goal_node().get_variable_name()) if ass.get_goal_node() else None

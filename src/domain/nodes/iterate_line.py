"""
Iterate Line Module.
Handles iteration over lists in INFERRA rule sets.
Implements access levels and strong typing where appropriate.

Phase 1 WS-3: IterateContext replaces the nested InferenceEngine for
progress tracking and self-evaluation. The new async feed_iterate_answer()
path uses IterateContext.progress instead of a sub-engineine's working
memory, and conclusions are tagged FactSource.INFERRED.
"""

import asyncio
import json
import re
from typing import Any, Dict, List, Optional, Tuple, Union

from src.domain.inference.assessment import Assessment
from src.domain.inference.assessment_state import AssessmentState
from src.domain.inference.inference_engine import InferenceEngine
from src.domain.iterate.iteration_engine import IterationEngine
from src.domain.state.fact_source import FactSource
from src.ports.iteration_port import IterationPort
from src.infrastructure.logging_config import get_logger
from src.domain.nodes.comparison_line import ComparisonLine
from src.domain.nodes.expression_conclusion_line import ExprConclusionLine
from src.domain.nodes.iterate_context import IterateContext
from src.domain.nodes.line_type import LineType
from src.domain.nodes.meta_data import MetaData
from src.domain.nodes.node import Node
from src.domain.nodes.node_set import NodeSet
from src.domain.fact_values import FactValue, FactValueType
from src.domain.nodes.value_conclusion_line import ValueConclusionLine
from src.domain.state.feature_flags import FeatureFlags
from src.domain.tokens import Token

# Protected Module-Level Logger (Access Level: Protected)
_logger = get_logger(__name__)


class IterateLine(Node):
    """
    IterateLine handles iteration over list-based rules.
    Implements private state with public accessors.
    
    Access Levels:
    - Public: API methods for external use
    - Protected: Internal helpers (single underscore)
    - Private: Internal state (double underscore)
    """
    
    # -------------------------------------------------------------------------
    # Private Access Level: Instance Variables (Name Mangling)
    # -------------------------------------------------------------------------
    def __init__(self, id: Optional[int] = None, parent_text: Optional[str] = None, 
                 tokens: Optional[Token] = None, meta_data: Optional[MetaData] = None):
        """
        Public Constructor: Initializes IterateLine.
        
        Args:
            id: Node ID
            parent_text: Text content of the node
            tokens: Tokenized representation
            meta_data: Metadata for the node
        """
        # Private instance variables (initialized in __init__ to avoid shared state)
        self.__number_of_target: Optional[str] = None
        self.__iterate_node_set: Optional[NodeSet] = None
        self.__given_list_name: Optional[str] = None
        self.__given_list_size: int = 0
        self.__iterate_ie: Optional[InferenceEngine] = None

        # Phase 1 WS-3: IterateContext replaces nested InferenceEngine for
        # progress tracking and self-evaluation.
        self.__context: Optional[IterateContext] = None
        # Per-node lock guards concurrent access to the progress dict.
        # Concurrency model: sessions are single-threaded by design; this lock
        # provides a safety net for async frameworks that may interleave coroutines.
        # Lazily initialized to avoid binding to the event loop at construction time,
        # which would fail if the object is created outside an async context.
        self._lock: Optional[asyncio.Lock] = None

        # Phase 2: IterationEngine delegates through FactStorePort with
        # truth-maintenance. Active when LEGACY_ITERATE=false.
        self._iteration_engine: Optional[IterationEngine] = None
        super().__init__(id=id, parent_text=parent_text, tokens=tokens, meta_data=meta_data)
        self._line_type = LineType.ITERATE

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Getters)
    # -------------------------------------------------------------------------
    def get_given_list_name(self) -> Optional[str]:
        """
        Public API: Returns the given list name.
        
        Returns:
            Given list name or None
        """
        return self.__given_list_name

    def get_number_of_target(self) -> Optional[str]:
        """
        Public API: Returns the number of target.
        
        Returns:
            Number of target or None
        """
        return self.__number_of_target

    def get_iterate_node_set(self) -> Optional[NodeSet]:
        """
        Public API: Returns the iterate node set.
        
        Returns:
            Iterate NodeSet or None
        """
        return self.__iterate_node_set

    def get_line_type(self) -> LineType:
        """
        Public API: Returns the line type.
        
        Returns:
            LineType.ITERATE
        """
        return LineType.ITERATE

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (IterateContext — Phase 1 WS-3)
    # -------------------------------------------------------------------------
    def _ensure_iterate_context(self, list_size: int, quantifier: Optional[str] = None) -> None:
        """
        Protected Helper: Initialise or validate the IterateContext.

        If no context exists, or the list_size differs from the current context,
        a fresh IterateContext is created. This guard ensures the context is
        always in a consistent state before progress tracking begins.

        Args:
            list_size: Number of items in the iterate list
            quantifier: Quantifier string (ALL / NONE / SOME / N). Falls back to
                self.__number_of_target if not supplied.
        """
        q = quantifier or self.__number_of_target or "ALL"
        if self.__context is not None and self.__context.list_size == list_size:
            return
        self.__context = IterateContext(
            list_name=self.__given_list_name or "",
            list_size=list_size,
            quantifier=q,
        )

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def feed_iterate_answer(
        self,
        question_name: str,
        node_value: Any,
        node_value_type: FactValueType,
        feature_flags: Optional[FeatureFlags] = None,
        parent_fact_store: "FactStorePort" = None,
    ) -> bool:
        """
        Public API: Thread-safe answer ingestion.

        When LEGACY_ITERATE=false, delegates to IterationEngine which routes
        through FactStorePort with truth-maintenance (ASSERTED wins over INFERRED).
        When LEGACY_ITERATE=true, uses the Phase 1 IterateContext path.

        Args:
            question_name: Name of the question being answered
            node_value: Value from user
            node_value_type: Type of the value
            feature_flags: Optional FeatureFlags snapshot governing path choice
            parent_fact_store: FactStorePort from parent AssessmentState (required
                for IterationEngine path)

        Returns:
            True if all list items have been answered, False otherwise
        """
        flags = feature_flags if feature_flags is not None else FeatureFlags()

        if not flags.legacy_iterate and parent_fact_store is not None:
            if self._iteration_engine is None:
                self._iteration_engine = IterationEngine(fact_store=parent_fact_store)
                q = self.__number_of_target or "ALL"
                self._iteration_engine.initialise(
                    list_size=self.__given_list_size,
                    quantifier=q,
                    list_name=self.__given_list_name or "",
                )
            idx = self._extract_ordinal_index(question_name)
            return await self._iteration_engine.record_answer(
                idx, question_name, node_value, node_value_type
            )

        # Phase 1 path: IterateContext-based answer recording
        async with self._get_lock():
            idx = self._extract_ordinal_index(question_name)
            if node_value_type == FactValueType.BOOLEAN:
                is_true = bool(node_value)
            elif isinstance(node_value, bool):
                is_true = node_value
            elif isinstance(node_value, str):
                is_true = node_value.strip().lower() == "true"
            else:
                is_true = bool(node_value)
            self.__context.progress[idx] = is_true
            return len(self.__context.progress) == self.__context.list_size

    def get_progress(self, feature_flags: Optional[FeatureFlags] = None) -> Tuple[int, int]:
        """
        Public API: Returns iterate progress (answered, total).

        When LEGACY_ITERATE=false and IterationEngine is active, delegates
        to IterationEngine.get_progress(). Otherwise uses IterateContext.

        Args:
            feature_flags: Optional FeatureFlags snapshot

        Returns:
            Tuple of (number of items answered, total list size)
        """
        flags = feature_flags if feature_flags is not None else FeatureFlags()
        if not flags.legacy_iterate and self._iteration_engine is not None:
            return self._iteration_engine.get_progress()
        if self.__context is None:
            return (0, 0)
        return (len(self.__context.progress), self.__context.list_size)

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Node Set Creation)
    # -------------------------------------------------------------------------
    def create_iterate_node_set(self, parent_node_set: NodeSet) -> NodeSet:
        """
        Public API: Creates iterate node set from parent node set.
        
        Args:
            parent_node_set: Parent NodeSet to create from
            
        Returns:
            New NodeSet for iteration
        """
        parent_node_dictionary = parent_node_set.get_node_dictionary()
        this_node_dictionary: Dict[str, Node] = dict()
        new_node_set = NodeSet()
        new_node_set.set_node_set_name(parent_node_set.get_node_set_name())

        new_node_set.add_node(self)
        this_node_dictionary[self._node_name] = self

        child_names = self._iterate_child_names(parent_node_set)
        first_child_name = child_names[0] if child_names else None

        for nth in range(1, self.__given_list_size + 1):
            for child_name in child_names:
                if child_name == first_child_name:
                    continue
                temp_child_node = parent_node_dictionary.get(child_name)
                if temp_child_node is None:
                    continue
                next_nth_in_string = self._ordinal(nth)
                temp_node = self._clone_iterate_child(
                    temp_child_node,
                    next_nth_in_string,
                )

                if temp_node:
                    self._register_iterate_clone(
                        new_node_set,
                        this_node_dictionary,
                        temp_node,
                        temp_child_node,
                        parent_node_set.get_node_set_name(),
                    )
                    dep_type = self._dependency_type(parent_node_set, self.get_node_name(), child_name)
                    new_node_set.get_graph().add_dependency_group(
                        self.get_node_name(),
                        dep_type,
                        {temp_node.get_node_name()},
                    )
                    self._create_iterate_node_set_aux(
                        parent_node_set,
                        new_node_set,
                        this_node_dictionary,
                        child_name,
                        temp_node.get_node_name(),
                        next_nth_in_string,
                    )

        new_node_set.set_node_dictionary(this_node_dictionary)
        new_node_set.set_fact_dictionary(parent_node_set.get_fact_dictionary())
        sorted_names = new_node_set.get_graph().topological_sort()
        if sorted_names:
            sorted_nodes = [this_node_dictionary[name] for name in sorted_names if name in this_node_dictionary]
            new_node_set.set_sorted_node_list(sorted_nodes)
        else:
            new_node_set.set_sorted_node_list(list(this_node_dictionary.values()))

        return new_node_set

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Answer Feeding)
    # -------------------------------------------------------------------------
    def iterate_feed_answers_with_json(self, given_json_string: Union[str, bytes], 
                                       parent_node_set: NodeSet,
                                       parent_assessment_state: AssessmentState, 
                                       assessment: Assessment) -> None:
        """
        Public API: Feeds answers from JSON string for iteration.
        
        Note: This is a legacy synchronous path. It is NOT protected by the
        asyncio.Lock used in feed_iterate_answer(). Concurrency model:
        sessions are single-threaded by design. Full deprecation of this
        path is deferred to a future phase once the API layer is refactored
        to use the async feed_iterate_answer() path directly.
        
        Args:
            given_json_string: JSON string containing iteration data
            parent_node_set: Parent NodeSet
            parent_assessment_state: Parent AssessmentState
            assessment: Current Assessment
        """
        json_object = json.loads(given_json_string)
        service_list = json_object[self._variable_name]

        self.__given_list_size = len(service_list)

        if self.__iterate_node_set is None:
            self.__iterate_node_set = self.create_iterate_node_set(parent_node_set)
            self.__iterate_ie = InferenceEngine(self.__iterate_node_set)
            
            if self.__iterate_ie.get_assessment_of_rule(self.get_node_name()) is None:
                self.__iterate_ie.add_assessment_into_assessment_list(
                    Assessment(self.__iterate_node_set, self.get_node_name()))

        while self._node_name not in self.__iterate_ie.get_assessment_state().get_working_memory().keys():
            next_question_node: Node = self.get_iterate_next_question(parent_node_set, parent_assessment_state)
            question_fvt_map = self.__iterate_ie.find_type_of_element_to_be_asked(next_question_node)
            
            for question in self.__iterate_ie.get_questions_from_node_to_be_asked(next_question_node):
                answer = str(json_object[self._variable_name]
                             [next_question_node.get_variable_name()[
                              0: next_question_node.get_variable_name().rindex(self._variable_name) + len(
                                  self._variable_name)]]
                             [next_question_node.get_variable_name()]).strip()

                self.__iterate_ie.feed_answer_to_node(next_question_node, question, 
                                                      FactValue(answer, FactValueType.STRING),
                                                      self.__iterate_ie.get_assessment_of_rule(self.get_node_name()))

            iterate_working_memory = self.__iterate_ie.get_assessment_state().get_working_memory()
            parent_assessment_state.set_fact(
                self._node_name,
                self.self_evaluate(iterate_working_memory),
                source=FactSource.INFERRED,
            )
            self._transfer_fact_value(iterate_working_memory, parent_assessment_state)

    def iterate_feed_answers(self, target_node: Node, question_name: str, node_value: Any,
                             node_value_type: FactValueType, parent_node_set: NodeSet,
                             parent_ast: AssessmentState, ass: Assessment,
                             feature_flags: Optional[FeatureFlags] = None) -> None:
        """
        Public API: Feeds answers for iteration. Dispatches between the legacy
        nested-InferenceEngine path and the new IterateContext path based on
        the LEGACY_ITERATE feature flag.

        - `LEGACY_ITERATE=true` (default): use the legacy `__iterate_ie`
          InferenceEngine path. Preserves pre-Phase-1 semantics for sessions
          that depend on the older iterate behaviour.
        - `LEGACY_ITERATE=false`: use the IterateContext-based path. Tracks
          progress per-ordinal in `__context.progress`, no nested engine.

        When `feature_flags` is None, defaults to a fresh FeatureFlags reading
        the current environment — production callers (InferenceEngine) pass
        the session's frozen flags so behaviour is start-of-session sticky.

        Args:
            target_node: Target node
            question_name: Name of the question
            node_value: Value from user
            node_value_type: Type of the value
            parent_node_set: Parent NodeSet
            parent_ast: Parent AssessmentState
            ass: Current Assessment
            feature_flags: Optional FeatureFlags snapshot governing path choice
        """
        flags = feature_flags if feature_flags is not None else FeatureFlags()
        if flags.legacy_iterate:
            self._iterate_feed_answers_legacy(
                target_node, question_name, node_value, node_value_type,
                parent_node_set, parent_ast, ass,
            )
        else:
            self._iterate_feed_answers_via_context(
                target_node, question_name, node_value, node_value_type,
                parent_node_set, parent_ast, ass,
            )

    def _iterate_feed_answers_legacy(self, target_node: Node, question_name: str, node_value: Any,
                                     node_value_type: FactValueType, parent_node_set: NodeSet,
                                     parent_ast: AssessmentState, ass: Assessment) -> None:
        """
        Protected Helper: Legacy iterate path using nested InferenceEngine.

        Preserved for `LEGACY_ITERATE=true`. Concurrency model: sessions are
        single-threaded by design — this path is NOT protected by the
        asyncio.Lock used in `feed_iterate_answer()`.
        """
        if self.__iterate_node_set is None:
            first_iterate_question_node = self._first_iterate_question_node(parent_node_set)
            if first_iterate_question_node is not None and question_name == first_iterate_question_node.get_node_name():
                self.__given_list_size = int(node_value)

            self.__iterate_node_set = self.create_iterate_node_set(parent_node_set)
            self.__iterate_ie = InferenceEngine(self.__iterate_node_set)

            if self.__iterate_ie.get_assessment_of_rule(self.get_node_name()) is None:
                self.__iterate_ie.add_assessment_into_assessment_list(
                    Assessment(self.__iterate_node_set, self.get_node_name()))

        self.__iterate_ie.get_assessment_of_rule(self.get_node_name()).set_node_to_be_asked(target_node)
        self.__iterate_ie.feed_answer_to_node(target_node, question_name, node_value,
                                              node_value_type,
                                              self.__iterate_ie.get_assessment_of_rule(self.get_node_name()))

        iterate_working_memory = self.__iterate_ie.get_assessment_state().get_working_memory()

        if self.can_be_self_evaluated(parent_ast.get_working_memory()):
            parent_ast.set_fact(
                self._node_name,
                self.self_evaluate(iterate_working_memory),
                source=FactSource.INFERRED,
            )
        self._transfer_fact_value(iterate_working_memory, parent_ast)

    def _iterate_feed_answers_via_context(self, target_node: Node, question_name: str, node_value: Any,
                                          node_value_type: FactValueType, parent_node_set: NodeSet,
                                          parent_ast: AssessmentState, ass: Assessment) -> None:
        """
        Protected Helper: New iterate path using IterateContext (no nested engine).

        Activated by `LEGACY_ITERATE=false`. The first question of the iterate
        block carries the list size as its value; subsequent answers populate
        `__context.progress` keyed by ordinal index.
        """
        if self.__given_list_size == 0 or self.__context is None:
            first_iterate_question_node = self._first_iterate_question_node(parent_node_set)
            if first_iterate_question_node is not None and question_name == first_iterate_question_node.get_node_name():
                self.__given_list_size = int(node_value)
            self._ensure_iterate_context(self.__given_list_size, self.__number_of_target or "ALL")

        idx = self._extract_ordinal_index(question_name)
        if idx >= 0 and self.__context is not None:
            if node_value_type == FactValueType.BOOLEAN:
                is_true = bool(node_value)
            elif isinstance(node_value, bool):
                is_true = node_value
            elif isinstance(node_value, str):
                is_true = node_value.strip().lower() == "true"
            else:
                is_true = bool(node_value)
            self.__context.progress[idx] = is_true

        if self.can_be_self_evaluated(parent_ast.get_working_memory()):
            parent_ast.set_fact(
                self._node_name,
                self.self_evaluate(parent_ast.get_working_memory()),
                source=FactSource.INFERRED,
            )

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Evaluation)
    # -------------------------------------------------------------------------
    def can_be_self_evaluated(self, working_memory: Dict[str, Any], feature_flags: Optional[FeatureFlags] = None) -> bool:
        """
        Public API: Checks if node can be self-evaluated.

        When LEGACY_ITERATE=false and IterationEngine is active, delegates
        to IterationEngine progress check. Otherwise uses IterateContext or
        the legacy InferenceEngine.

        Args:
            working_memory: Current working memory dictionary
            feature_flags: Optional FeatureFlags snapshot

        Returns:
            True if can be self-evaluated, False otherwise
        """
        flags = feature_flags if feature_flags is not None else FeatureFlags()

        if not flags.legacy_iterate and self._iteration_engine is not None:
            answered, total = self._iteration_engine.get_progress()
            return answered == total and total > 0

        if self.__context is not None:
            return (
                len(self.__context.progress) == self.__context.list_size
                and self.__context.list_size > 0
            )

        # Legacy path
        if self.__iterate_ie is not None:
            child_names = self._iterable_child_names(self.__iterate_ie.get_node_set())
            determined = [
                name for name in child_names
                if working_memory.get(name) is not None
                and getattr(working_memory.get(name), "get_value", lambda: None)() is not None
            ]
            mandatory_check = getattr(
                self.__iterate_ie,
                "has_all_mandatory_child_answered",
                lambda _node_name: True,
            )

            if self.__given_list_size == len(determined) \
                    and mandatory_check(self.get_node_name()):
                return True

        return False

    def self_evaluate(self, working_memory: Dict[str, Any], feature_flags: Optional[FeatureFlags] = None) -> FactValue:
        """
        Public API: Self-evaluates the iterate line.

        When LEGACY_ITERATE=false and IterationEngine is active, delegates
        to IterationEngine.evaluate(). Otherwise uses IterateContext or the
        legacy InferenceEngine path.

        Args:
            working_memory: Current working memory dictionary
            feature_flags: Optional FeatureFlags snapshot

        Returns:
            FactValue result of evaluation
        """
        flags = feature_flags if feature_flags is not None else FeatureFlags()

        if not flags.legacy_iterate and self._iteration_engine is not None:
            return self._iteration_engine.evaluate()

        if self.__context is not None:
            return self._self_evaluate_from_context()

        # Legacy path: delegate to nested InferenceEngine
        number_if_true_children: int = self._number_of_true_children(working_memory)
        return self._evaluate_quantifier(number_if_true_children, self.__given_list_size)

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Iterate Next Question)
    # -------------------------------------------------------------------------
    def get_iterate_next_question(
        self,
        parent_node_set: NodeSet,
        parent_ast: AssessmentState,
    ) -> Optional[Node]:
        """
        Public API: Gets next question for iteration.
        
        Args:
            parent_node_set: Parent NodeSet
            parent_ast: Parent AssessmentState
            
        Returns:
            Next question Node or None
        """
        if self.__iterate_node_set is None and self.__given_list_size != 0:
            self.__iterate_node_set = self.create_iterate_node_set(parent_node_set)
            self.__iterate_ie = InferenceEngine(self.__iterate_node_set)
            
            if self.__iterate_ie.get_assessment_of_rule(self.get_node_name()) is None:
                self.__iterate_ie.add_assessment_into_assessment_list(
                    Assessment(self.__iterate_node_set, self.get_node_name()))

        first_iterate_question_node = self._first_iterate_question_node(parent_node_set)
        question_node: Optional[Node] = None

        if str(self._value.get_value()) not in parent_ast.get_working_memory().keys():
            if first_iterate_question_node is not None and first_iterate_question_node.get_node_name() not in parent_ast.get_working_memory().keys():
                question_node = first_iterate_question_node
            else:
                if not self.can_be_self_evaluated(parent_ast.get_working_memory()):
                    question_node = self.__iterate_ie.get_next_question(
                        self.__iterate_ie.get_assessment_of_rule(self.get_node_name()))

        return question_node

    # -------------------------------------------------------------------------
    # Protected Access Level: Internal Helpers (Single Underscore)
    # -------------------------------------------------------------------------
    def _self_evaluate_from_context(self) -> FactValue:
        """
        Protected Helper: Self-evaluate using IterateContext progress dict.

        Returns:
            FactValue result based on progress and quantifier
        """
        true_count = sum(1 for v in self.__context.progress.values() if v)
        return self._evaluate_quantifier(true_count, self.__context.list_size)

    def _evaluate_quantifier(self, true_count: int, list_size: int) -> FactValue:
        """
        Protected Helper: Evaluates the quantifier against a true count.

        Args:
            true_count: Number of items that evaluated to True
            list_size: Total number of items in the list

        Returns:
            FactValue result
        """
        q = self.__number_of_target or "ALL"
        if q == "ALL":
            return FactValue(true_count == list_size)
        if q == "NONE":
            return FactValue(true_count == 0)
        if q == "SOME":
            return FactValue(true_count > 0)
        try:
            return FactValue(true_count == int(q))
        except (ValueError, TypeError):
            return FactValue(False)

    def _extract_ordinal_index(self, question_name: str) -> int:
        """
        Protected Helper: Extract the ordinal index from a question name.

        Question names for iterate children follow the pattern:
            "1st  variable_name  ..." or "2nd  variable_name  ..."
        This method extracts the leading ordinal number.

        Args:
            question_name: Question name containing an ordinal prefix

        Returns:
            The ordinal index (1-based), or len(progress)+1 as fallback
        """
        match = re.match(r"(\d+)", question_name.strip())
        if match:
            return int(match.group(1))
        # Fallback: append to end of progress dict
        if self.__context is not None:
            return len(self.__context.progress) + 1
        return 1

    def _create_iterate_node_set_aux(
        self,
        parent_node_set: NodeSet,
        iterate_node_set: NodeSet,
        this_node_dictionary: Dict[str, Node],
        original_parent_name: str,
        modified_parent_name: str,
        next_nth_in_string: str,
    ) -> None:
        """
        Protected Helper: Recursively clone descendants for one iterate item.
        """
        parent_graph = parent_node_set.get_graph()
        if parent_graph is None:
            return

        parent_node_dictionary = parent_node_set.get_node_dictionary()
        for child_name in parent_graph.get_children_flat(original_parent_name):
            temp_child_node = parent_node_dictionary.get(child_name)
            if temp_child_node is None:
                continue

            temp_node_name = (
                next_nth_in_string
                + "  "
                + self.get_variable_name()
                + "  "
                + temp_child_node.get_node_name()
            )
            temp_node = this_node_dictionary.get(temp_node_name)
            if temp_node is None:
                temp_node = self._clone_iterate_child(
                    temp_child_node,
                    next_nth_in_string,
                )

            if temp_node and temp_node.get_node_name() not in this_node_dictionary:
                self._register_iterate_clone(
                    iterate_node_set,
                    this_node_dictionary,
                    temp_node,
                    temp_child_node,
                    parent_node_set.get_node_set_name(),
                )
                dep_type = self._dependency_type(parent_node_set, original_parent_name, child_name)
                iterate_node_set.get_graph().add_dependency_group(
                    modified_parent_name,
                    dep_type,
                    {temp_node.get_node_name()},
                )
                self._create_iterate_node_set_aux(
                    parent_node_set,
                    iterate_node_set,
                    this_node_dictionary,
                    child_name,
                    temp_node.get_node_name(),
                    next_nth_in_string,
                )

    def _iterate_child_names(self, parent_node_set: NodeSet) -> List[str]:
        graph = parent_node_set.get_graph()
        if graph is None:
            return []
        children = list(graph.get_children_flat(self.get_node_name()))
        return sorted(
            children,
            key=lambda name: (
                graph.lookup_by_name(name)
                if graph.lookup_by_name(name) is not None
                else 10**9,
                name,
            ),
        )

    def _first_iterate_question_node(self, parent_node_set: NodeSet) -> Optional[Node]:
        child_names = self._iterate_child_names(parent_node_set)
        if not child_names:
            return None
        return parent_node_set.get_node_dictionary().get(child_names[0])

    def _iterable_child_names(self, node_set: NodeSet) -> List[str]:
        child_names = self._iterate_child_names(node_set)
        if not child_names:
            return []
        return child_names[1:]

    def _dependency_type(self, node_set: NodeSet, parent_name: str, child_name: str) -> int:
        graph = node_set.get_graph()
        if graph is None:
            return DependencyType.get_or()
        dep_type = graph.get_dependency_type(parent_name, child_name)
        return dep_type if dep_type != -1 else DependencyType.get_or()

    def _clone_iterate_child(
        self,
        child_node: Node,
        nth: str,
    ) -> Optional[Node]:
        node_text = nth + "  " + self.get_variable_name() + "  " + child_node.get_node_name()
        line_type = child_node.get_line_type()
        temp_node: Optional[Node] = None

        if line_type == LineType.VALUE_CONCLUSION:
            temp_node = ValueConclusionLine(
                node_text=node_text,
                tokens=child_node.get_tokens(),
            )
        elif line_type == LineType.COMPARISON:
            temp_node = ComparisonLine(
                node_text=node_text,
                tokens=child_node.get_tokens(),
            )
            temp_node_fact_value = temp_node.get_rhs()
            if temp_node_fact_value.get_value_type().value == FactValueType.STRING.value:
                temp_fact_value = FactValue(
                    nth + "  " + self.get_variable_name() + "  " + temp_node_fact_value.get_value(),
                    FactValueType.STRING,
                )
                temp_node.set_value(temp_fact_value)
        elif line_type == LineType.EXPR_CONCLUSION:
            temp_node = ExprConclusionLine(
                node_text=node_text,
                tokens=child_node.get_tokens(),
            )
        return temp_node

    def _register_iterate_clone(
        self,
        iterate_node_set: NodeSet,
        this_node_dictionary: Dict[str, Node],
        temp_node: Node,
        source_node: Node,
        source_name: str,
    ) -> None:
        temp_node.set_node_line(source_node.get_node_line() or 0)
        temp_node.refresh_stable_node_id(source_name)
        iterate_node_set.add_node(temp_node)
        this_node_dictionary[temp_node.get_node_name()] = temp_node

    def _transfer_fact_value(self, working_memory_one: Dict[str, Any], 
                             working_memory_two: Dict[str, Any]) -> None:
        """
        Protected Helper: Transfers fact values between working memories.
        
        Args:
            working_memory_one: Source working memory
            working_memory_two: Destination working memory
        """
        key_sets_one = set(working_memory_one.keys())
        for each_key_one in key_sets_one:
            if each_key_one not in working_memory_two.keys():
                working_memory_two[each_key_one] = working_memory_one[each_key_one]

    def _number_of_true_children(self, working_memory: Dict[str, Any]) -> int:
        """
        Protected Helper: Counts number of true children.
        
        Args:
            working_memory: Current working memory dictionary
            
        Returns:
            Count of true children
        """
        if self.__iterate_ie is None:
            return 0
        node_set = self.__iterate_ie.get_node_set()
        true_count = 0
        for child_name in self._iterable_child_names(node_set):
            fact_value = working_memory.get(child_name)
            if fact_value is not None and str(fact_value.get_value()).lower() == "true":
                true_count += 1
        return true_count

    def _find_nth(self, working_memory: Dict[str, Any]) -> int:
        """
        Protected Helper: Finds nth iteration.
        
        Args:
            working_memory: Current working memory dictionary
            
        Returns:
            Nth iteration number
        """
        nth_list: List[int] = []
        for index in range(1, self.__given_list_size):
            if working_memory.get(self._ordinal(index) + "  " + self._variable_name) is not None:
                nth_list.append(index)
        return len(nth_list)

    @staticmethod
    def _ordinal(i: int) -> str:
        """
        Protected Helper: Converts number to ordinal string.
        
        Args:
            i: Number to convert
            
        Returns:
            Ordinal string (1st, 2nd, 3rd, etc.)
        """
        suffixes = ["th", "st", "nd", "rd", "th", "th", "th", "th", "th", "th"]
        nth_case = i % 100

        if nth_case == 11 or nth_case == 12 or nth_case == 13:
            return str(i) + 'th'
        else:
            return str(i) + suffixes[i % 10]

    # -------------------------------------------------------------------------
    # Special Methods
    # -------------------------------------------------------------------------
    def __repr__(self) -> str:
        """
        Public API: String representation of the object.
        
        Returns:
            JSON string representation
        """
        return json.dumps(self.__dict__)

    # -------------------------------------------------------------------------
    # Protected Access Level: Internal Helpers (Single Underscore)
    # -------------------------------------------------------------------------
    def initialisation(self, parent_text: str, tokens: Token) -> None:
        self._initialisation(parent_text, tokens)

    def _initialisation(self, parent_text: str, tokens: Token) -> None:
        """
        Protected Helper: Initializes the iterate line.
        
        Args:
            parent_text: Text content of the node
            tokens: Tokenized representation
        """
        _logger.info("Generating Iterate Line with : " + str(parent_text))

        self._node_name = parent_text
        self.__number_of_target = tokens.get_tokens_list()[0]
        self._variable_name = tokens.get_tokens_list()[1]
        token_string_list_size = len(tokens.get_tokens_string_list())
        last_token: str = tokens.get_tokens_list()[token_string_list_size - 1]
        last_token_string: str = tokens.get_tokens_string_list()[token_string_list_size - 1]
        self.set_value(last_token_string, last_token)
        self.__given_list_name = last_token

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.ports.fact_store_port import FactStorePort


@dataclass
class InferenceContext:
    """Session-level state shared by orchestrator, convergence, and trace code."""

    session_id: str
    rule_name: str
    target: str
    mandatory: List[str]
    fact_store: FactStorePort
    started_at: datetime = field(default_factory=datetime.utcnow)
    iteration_count: int = 0
    ontology_delta: int = 0
    ontology_profile: str = "custom"
    ontology_profile_source: str = "environment"
    ontology_flags: Dict[str, Any] = field(default_factory=dict)
    question_strategy_name: str = "conservative"
    prov_o_trace: Optional[str] = None
    convergence_trace: List[str] = field(default_factory=list)
    ontology_pre_reasoned: bool = False
    ontology_snapshot_ref: Optional[str] = None
    ontology_snapshot_hash: Optional[str] = None
    ontology_graph_uris: List[str] = field(default_factory=list)
    ontology_binding_count: int = 0
    ontology_binding_ambiguity_count: int = 0
    ontology_missing_binding_count: int = 0
    ontology_advisory_trace: List[Dict[str, Any]] = field(default_factory=list)
    ontology_advisory_suggestions: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    ontology_value_suggestions: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    ontology_constraint_suggestions: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    ontology_auto_answer_trace: List[Dict[str, Any]] = field(default_factory=list)
    ontology_reasoner_enabled: bool = False
    ontology_reasoning_applied: bool = False
    ontology_reasoning_confidence_threshold: float = 0.85
    ontology_reasoning_min_hierarchy_depth: int = 1
    ontology_reasoning_max_closure_depth: int = 10
    ontology_derived_facts: List[str] = field(default_factory=list)
    ontology_materialization_trace: List[Dict[str, Any]] = field(default_factory=list)
    semantic_question_strategy_trace: List[Dict[str, Any]] = field(default_factory=list)
    semantic_questions_skipped: List[Dict[str, Any]] = field(default_factory=list)
    deferred_semantic_questions: List[Dict[str, Any]] = field(default_factory=list)
    post_decision_answer_names: List[str] = field(default_factory=list)
    semantic_completion_status: str = "NOT_STARTED"
    semantic_completion_policy: str = "UNSPECIFIED"
    decision_locked: bool = False
    original_decision_name: Optional[str] = None
    original_decision_value: Optional[str] = None
    semantic_divergence: Optional[Dict[str, Any]] = None
    reasoning_mode: str = "DEDUCTION"
    confidence: float = 1.0
    hypothesis_trace: List[Dict[str, Any]] = field(default_factory=list)
    induction_job_id: Optional[str] = None
    abduction_attempted: bool = False
    abduction_count: int = 0

    def increment_iteration(self) -> None:
        self.iteration_count += 1

    def set_ontology_delta(self, delta: int) -> None:
        self.ontology_delta = delta

    def record_abduction_attempt(self, hypotheses: List[Dict[str, Any]]) -> None:
        self.abduction_attempted = True
        self.abduction_count += 1
        self.reasoning_mode = "ABDUCTION"
        self.hypothesis_trace.extend(dict(item) for item in hypotheses)
        if hypotheses:
            self.confidence = float(hypotheses[0].get("confidence", self.confidence))

    def set_induction_job(self, job_id: str) -> None:
        self.induction_job_id = job_id
        self.reasoning_mode = "INDUCTION"
        self.confidence = min(self.confidence, 0.5)

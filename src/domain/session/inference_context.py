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
    question_strategy_name: str = "conservative"
    prov_o_trace: Optional[str] = None
    convergence_trace: List[str] = field(default_factory=list)
    ontology_pre_reasoned: bool = False
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

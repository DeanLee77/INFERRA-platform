from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class Hypothesis:
    fact_name: str
    suggested_value: str
    confidence: float
    dependency_path: List[str] = field(default_factory=list)
    ontology_consistent: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fact_name": self.fact_name,
            "suggested_value": self.suggested_value,
            "confidence": self.confidence,
            "dependency_path": list(self.dependency_path),
            "ontology_consistent": self.ontology_consistent,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "Hypothesis":
        return cls(
            fact_name=str(payload.get("fact_name", "")),
            suggested_value=str(payload.get("suggested_value", "")),
            confidence=float(payload.get("confidence", 0.0)),
            dependency_path=list(payload.get("dependency_path", [])),
            ontology_consistent=bool(payload.get("ontology_consistent", True)),
        )

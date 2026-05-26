from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class GoalMapping:
    node_name: Optional[str]
    confidence: float
    fallback: bool = False
    message: str = ""
    prompt_version: str = "null"

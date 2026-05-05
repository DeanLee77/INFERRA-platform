"""
Inference Session Module.
Represents a single inference session with its associated state.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from src.domain.inference.inference_engine import InferenceEngine
from src.domain.inference.assessment import Assessment
from src.domain.state.feature_flags import FeatureFlags


@dataclass
class InferenceSession:
    """
    InferenceSession represents an active inference workflow.

    It holds the inference engine, assessment state, and a frozen feature-flag
    snapshot for a particular user session, along with metadata for session
    management.

    Attributes:
        session_id: Unique identifier for this session
        rule_name: Name of the rule being evaluated
        target_node_name: Name of the target/goal node
        inference_engine: The inference engine instance
        assessment: The assessment instance
        feature_flags: Frozen FeatureFlags snapshot for this session — flags
            cannot flip mid-session, so this captures the values at start
        created_at: When this session was created
        last_accessed: When this session was last accessed
    """
    session_id: str
    rule_name: str
    target_node_name: str
    inference_engine: InferenceEngine
    assessment: Assessment
    feature_flags: Optional[FeatureFlags] = None
    version: int = 0
    owner_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_accessed: datetime = field(default_factory=datetime.utcnow)

    def touch(self) -> None:
        """Update the last_accessed timestamp."""
        self.last_accessed = datetime.utcnow()

    @property
    def is_valid(self) -> bool:
        """Check if the session has valid engine and assessment."""
        return (
            self.inference_engine is not None and
            self.assessment is not None
        )

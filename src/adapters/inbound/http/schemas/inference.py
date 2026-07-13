"""
Pydantic schemas for inference API endpoints.
"""

from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


# =============================================================================
# Session Management
# =============================================================================

class SessionCreateRequest(BaseModel):
    """Request to create a new inference session."""
    rule_name: str = Field(..., description="Name of the rule to evaluate")
    target_node_name: str = Field(..., description="Name of the target/goal node")
    ontology_profile: Optional[str] = Field(
        None,
        description=(
            "Optional per-session ontology assistance profile: off, advisory, "
            "auto_answer, reasoning, or full_semantic_pilot"
        ),
    )
    ontology_flags: Optional[Dict[str, bool]] = Field(
        None,
        description=(
            "Optional per-session ontology boolean overrides. Supported keys include "
            "advisory_enabled, auto_answer_enabled, reasoning_enabled, and "
            "question_strategy_enabled."
        ),
    )


class SessionCreateResponse(BaseModel):
    """Response after creating an inference session."""
    session_id: str = Field(..., description="Unique session identifier")
    rule_name: str = Field(..., description="Name of the rule being evaluated")
    target_node_name: str = Field(..., description="Name of the target node")
    ontology_profile: Optional[str] = Field(None, description="Resolved ontology assistance profile")
    llm_configuration: Optional[Dict[str, Any]] = Field(
        None,
        description="Redacted start-of-session AXIOM/AEGIS LLM configuration snapshot",
    )


class SessionListItem(BaseModel):
    """Summary of an active inference session."""
    session_id: str = Field(..., description="Unique session identifier")
    rule_name: str = Field(..., description="Name of the rule being evaluated")
    target_node_name: str = Field(..., description="Name of the target node")
    created_at: Optional[str] = Field(None, description="Session creation timestamp")
    last_accessed: Optional[str] = Field(None, description="Most recent access timestamp")


class SessionListResponse(BaseModel):
    """Response containing active inference sessions."""
    sessions: List[SessionListItem] = Field(default_factory=list, description="Active sessions")
    total_count: int = Field(0, description="Number of active sessions")


class SessionDeleteResponse(BaseModel):
    """Response after deleting an inference session."""
    deleted: bool = Field(..., description="Whether the session was deleted")
    session_id: str = Field(..., description="Session identifier")


class MLSessionCreateRequest(BaseModel):
    """Request to create an ML-enhanced inference session."""
    rule_name: str = Field(..., description="Name of the rule to evaluate")
    target_node_name: str = Field(..., description="Name of the target/goal node")
    ontology_profile: Optional[str] = Field(
        None,
        description=(
            "Optional per-session ontology assistance profile: off, advisory, "
            "auto_answer, reasoning, or full_semantic_pilot"
        ),
    )
    ontology_flags: Optional[Dict[str, bool]] = Field(
        None,
        description=(
            "Optional per-session ontology boolean overrides. Supported keys include "
            "advisory_enabled, auto_answer_enabled, reasoning_enabled, and "
            "question_strategy_enabled."
        ),
    )


# =============================================================================
# Question/Answer Flow
# =============================================================================

class IterateProgress(BaseModel):
    """Progress indicator for an iterate node."""
    answered: int = Field(..., description="Number of iterate questions answered")
    total: int = Field(..., description="Total iterate questions")
    quantifier: str = Field("ALL", description="Quantifier for evaluation (ALL/NONE/SOME/AT LEAST N/AT MOST N/EXACTLY N)")
    list_name: str = Field("", description="Name of the iterate list")


class QuestionOption(BaseModel):
    """A selectable option for a LIST question."""
    label: str = Field(..., description="Display label for the option")
    value: Union[bool, int, float, str] = Field(..., description="Value to feed as the answer")
    value_type: str = Field(..., description="Fact value type for the option")


class QuestionItem(BaseModel):
    """A single question to be answered."""
    question_text: str = Field(..., description="The question text")
    question_value_type: str = Field(..., description="Expected answer type (boolean, string, number, etc.)")
    control: Optional[str] = Field(None, description="Preferred UI control for the question")
    options: List[QuestionOption] = Field(default_factory=list, description="Selectable options for LIST questions")
    selection_mode: Optional[str] = Field(None, description="Selection mode for option controls")
    semantic_suggestions: List[Dict[str, Any]] = Field(default_factory=list, description="Ontology-derived advisory suggestions")


class NextQuestionResponse(BaseModel):
    """Response containing the next questions to answer."""
    session_id: str = Field(..., description="Session identifier")
    questions: List[QuestionItem] = Field(default_factory=list, description="List of questions")
    has_more_questions: bool = Field(..., description="Whether more questions remain")
    iterate_progress: Optional[IterateProgress] = Field(None, description="Progress of current iterate node (if applicable)")
    convergence_state: str = Field("PENDING", description="Current convergence state for the session")
    question_flow_state: str = Field("AWAITING_INPUT", description="Question flow state for UI recovery handling")
    blocked_reason: Optional[str] = Field(None, description="Machine-readable reason when no askable question remains")
    blocked_detail: Optional[str] = Field(None, description="Human-readable recovery detail for blocked question flow")


class AnswerEntry(BaseModel):
    """An answer entry from the user."""
    type: str = Field(..., description="Answer type (boolean, string, number, etc.)")
    answer: Union[bool, int, float, str, List[Any]] = Field(..., description="The answer value")


class IterateAnswerPayload(BaseModel):
    """Payload for submitting an iterate answer via /feed-answer."""
    question: str = Field(..., description="The question being answered")
    answer: AnswerEntry = Field(..., description="The answer")
    index: int = Field(..., ge=1, description="Ordinal index of the iterate item (1-based)")
    list_name: str = Field("", description="Name of the iterate list")


class FeedAnswerRequest(BaseModel):
    """Request to submit an answer to a question."""
    question: str = Field(..., description="The question being answered")
    answer: AnswerEntry = Field(..., description="The answer")
    answer_context: Optional[str] = Field(
        None,
        description="Optional context for audit metadata, e.g. FULL_SEMANTIC_COMPLETION",
    )


class DeferQuestionRequest(BaseModel):
    """Request to defer a semantic-completion question without asserting a fact."""
    question: str = Field(..., description="Question to defer")
    node_name: Optional[str] = Field(None, description="Related node name, if known")
    reason: Optional[str] = Field(None, description="Reason for deferring the question")
    defer_all_remaining: bool = Field(
        False,
        description="Whether generation should stop after recording this deferred question",
    )


class DeferQuestionResponse(BaseModel):
    """Response after deferring a semantic-completion question."""
    deferred: bool = Field(..., description="Whether the question was recorded as deferred")
    session_id: str = Field(..., description="Session identifier")
    question: str = Field(..., description="Deferred question")
    deferred_count: int = Field(..., description="Total deferred semantic question count")
    defer_all_remaining: bool = Field(False, description="Whether remaining questions were deferred")


class FeedAnswerResponse(BaseModel):
    """Response after submitting an answer."""
    has_more_questions: bool = Field(..., description="Whether more questions remain")
    goal_rule_name: Optional[str] = Field(None, description="Goal node name if reached")
    goal_rule_value: Optional[str] = Field(None, description="Goal node value if reached")
    goal_rule_type: Optional[str] = Field(None, description="Goal node type if reached")


class ResetAnswerRequest(BaseModel):
    """Request to reset (undo) a previously answered question."""
    question: str = Field(..., description="The question to reset")


class EditAnswerResponse(BaseModel):
    """Response after resetting an answer."""
    has_more_questions: bool = Field(..., description="Whether more questions remain")
    goal_rule_name: Optional[str] = Field(None, description="Goal node name if reached")
    goal_rule_value: Optional[str] = Field(None, description="Goal node value if reached")
    goal_rule_type: Optional[str] = Field(None, description="Goal node type if reached")


# =============================================================================
# Summary
# =============================================================================

class SummaryItem(BaseModel):
    """A single item in the assessment summary."""
    node_text: str = Field(..., description="Node/question text")
    node_value: str = Field(..., description="Node value")
    fact_source: Optional[str] = Field(None, description="Fact source layer (ASSERTED, INFERRED, SEMANTIC)")


class SummaryResponse(BaseModel):
    """Response containing assessment summary."""
    session_id: str = Field(..., description="Session identifier")
    summary: List[SummaryItem] = Field(default_factory=list, description="Summary items")
    total_count: int = Field(0, description="Total number of summary items")
    offset: int = Field(0, description="Offset of first item in this page")
    limit: int = Field(0, description="Maximum number of items in this page (0 = all)")
    reasoning_mode: str = Field("DEDUCTION", description="Reasoning mode used by the session")
    confidence: float = Field(1.0, description="Current reasoning confidence")
    status: str = Field("PENDING", description="Current convergence status")
    origin_job_id: Optional[str] = Field(None, description="Async induction job that influenced the session, if any")


class TraceResponse(BaseModel):
    """Response containing a PROV-O trace for an inference session."""
    session_id: str = Field(..., description="Session identifier")
    format: str = Field(..., description="Trace serialization format")
    trace: str = Field(..., description="Serialized PROV-O trace")
    reasoning_mode: str = Field("DEDUCTION", description="Reasoning mode used by the session")
    confidence: float = Field(1.0, description="Current reasoning confidence")


# =============================================================================
# History
# =============================================================================

class UpdateHistoryRequest(BaseModel):
    """Request to update inference history."""
    rule_name: str = Field(..., description="Name of the rule")


class UpdateHistoryResponse(BaseModel):
    """Response after updating history."""
    updated: bool = Field(..., description="Whether history was updated")


# =============================================================================
# Error Response
# =============================================================================

class ErrorResponse(BaseModel):
    """Standard error response."""
    success: bool = Field(False, description="Always false for errors")
    error: str = Field(..., description="Error message")
    detail: Optional[Union[str, dict]] = Field(None, description="Additional error details")

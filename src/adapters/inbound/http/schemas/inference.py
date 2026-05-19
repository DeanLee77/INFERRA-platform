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


class SessionCreateResponse(BaseModel):
    """Response after creating an inference session."""
    session_id: str = Field(..., description="Unique session identifier")
    rule_name: str = Field(..., description="Name of the rule being evaluated")
    target_node_name: str = Field(..., description="Name of the target node")


class MLSessionCreateRequest(BaseModel):
    """Request to create an ML-enhanced inference session."""
    rule_name: str = Field(..., description="Name of the rule to evaluate")
    target_node_name: str = Field(..., description="Name of the target/goal node")


# =============================================================================
# Question/Answer Flow
# =============================================================================

class IterateProgress(BaseModel):
    """Progress indicator for an iterate node."""
    answered: int = Field(..., description="Number of iterate questions answered")
    total: int = Field(..., description="Total iterate questions")
    quantifier: str = Field("ALL", description="Quantifier for evaluation (ALL/NONE/SOME/N)")
    list_name: str = Field("", description="Name of the iterate list")


class QuestionItem(BaseModel):
    """A single question to be answered."""
    question_text: str = Field(..., description="The question text")
    question_value_type: str = Field(..., description="Expected answer type (boolean, string, number, etc.)")


class NextQuestionResponse(BaseModel):
    """Response containing the next questions to answer."""
    session_id: str = Field(..., description="Session identifier")
    questions: List[QuestionItem] = Field(default_factory=list, description="List of questions")
    has_more_questions: bool = Field(..., description="Whether more questions remain")
    iterate_progress: Optional[IterateProgress] = Field(None, description="Progress of current iterate node (if applicable)")
    convergence_state: str = Field("PENDING", description="Current convergence state for the session")


class AnswerEntry(BaseModel):
    """An answer entry from the user."""
    type: str = Field(..., description="Answer type (boolean, string, number, etc.)")
    answer: Union[bool, int, float, str] = Field(..., description="The answer value (scalar types only)")


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

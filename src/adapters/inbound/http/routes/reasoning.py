from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.adapters.outbound.llm.factory import create_llm_orchestrator
from src.adapters.outbound.reasoning.celery_induction_adapter import CeleryInductionAdapter
from src.adapters.outbound.reasoning.factory import create_abduction_adapter, create_induction_adapter
from src.adapters.inbound.http.routes.metrics import (
    abduction_hypothesis_count,
    abduction_total,
    induction_total,
    llm_call_total,
    llm_confidence_score,
    llm_response_length,
    reasoning_route_total,
)
from src.domain.state.feature_flags import FeatureFlags
from src.infrastructure.reasoning_tracing import reasoning_span

router = APIRouter(prefix="/api/v1/reasoning", tags=["reasoning"])


class AbductionRequest(BaseModel):
    target: str
    working_memory: Dict[str, Any] = Field(default_factory=dict)
    graph_snapshot: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class AbductionResponse(BaseModel):
    target: str
    hypotheses: List[Dict[str, Any]]


class InductionStartRequest(BaseModel):
    session_ids: List[str]
    rule_name: str
    enabled: bool = True


class InductionStatusResponse(BaseModel):
    job_id: str
    status: str
    rule_name: str = ""
    candidate_rules: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


class PromotionRequest(BaseModel):
    job_id: str
    candidate_rule: str


class GoalMappingRequest(BaseModel):
    user_query: str
    rule_name: str
    enabled: bool = True


class GoalMappingResponse(BaseModel):
    node_name: Optional[str] = None
    confidence: float = 0.0
    fallback: bool = False
    message: str = ""
    prompt_version: str = "null"


class QuestionPromptRequest(BaseModel):
    node_name: str
    variable_name: str
    ontology_context: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class QuestionPromptResponse(BaseModel):
    prompt: str


class ExplanationRequest(BaseModel):
    trace_content: str
    trace_format: str = "turtle"
    session_id: str = ""
    enabled: bool = True


class ExplanationResponse(BaseModel):
    explanation: str
    trace_format: str
    prompt_version: str = "llm-orchestrator-v1"


@router.post("/abduct", response_model=AbductionResponse)
async def abduct(request: AbductionRequest) -> AbductionResponse:
    adapter = create_abduction_adapter(
        FeatureFlags(abduction_enabled=request.enabled)
    )
    try:
        with reasoning_span(
            "abduction.propose",
            {
                "abduction.target": request.target,
                "abduction.working_memory_count": len(request.working_memory),
            },
        ):
            hypotheses = adapter.propose_hypotheses(
                request.target,
                request.working_memory,
                request.graph_snapshot,
            )
    except Exception:
        abduction_total.labels(status="error").inc()
        reasoning_route_total.labels(mode="ABDUCTION", action="ERROR").inc()
        raise
    abduction_total.labels(status="success").inc()
    abduction_hypothesis_count.observe(len(hypotheses))
    reasoning_route_total.labels(
        mode="ABDUCTION" if hypotheses else "DEDUCTION",
        action="INJECT_HYPOTHESIS" if hypotheses else "NO_HYPOTHESIS",
    ).inc()
    return AbductionResponse(target=request.target, hypotheses=hypotheses)


@router.post("/goal", response_model=GoalMappingResponse)
async def map_goal(request: GoalMappingRequest) -> GoalMappingResponse:
    orchestrator = create_llm_orchestrator(
        FeatureFlags(llm_enhancements=request.enabled)
    )
    try:
        with reasoning_span(
            "llm.goal_mapping",
            {"llm.rule_name": request.rule_name},
        ):
            result = orchestrator.map_nl_to_goal(request.user_query, request.rule_name)
    except Exception:
        llm_call_total.labels(operation="goal_mapping", status="error").inc()
        raise
    status = "fallback" if result.get("fallback") else "success"
    llm_call_total.labels(operation="goal_mapping", status=status).inc()
    llm_confidence_score.observe(float(result.get("confidence", 0.0)))
    return GoalMappingResponse(**result)


@router.post("/question-prompt", response_model=QuestionPromptResponse)
async def enhance_question_prompt(request: QuestionPromptRequest) -> QuestionPromptResponse:
    orchestrator = create_llm_orchestrator(
        FeatureFlags(llm_enhancements=request.enabled)
    )
    try:
        with reasoning_span(
            "llm.question_prompt",
            {"llm.node_name": request.node_name},
        ):
            prompt = orchestrator.enhance_question_prompt(
                request.node_name,
                request.variable_name,
                request.ontology_context,
            )
    except Exception:
        llm_call_total.labels(operation="question_prompt", status="error").inc()
        raise
    llm_call_total.labels(operation="question_prompt", status="success").inc()
    llm_response_length.observe(len(prompt))
    return QuestionPromptResponse(prompt=prompt)


@router.post("/explain", response_model=ExplanationResponse)
async def explain_trace(request: ExplanationRequest) -> ExplanationResponse:
    orchestrator = create_llm_orchestrator(
        FeatureFlags(llm_enhancements=request.enabled)
    )
    try:
        with reasoning_span(
            "llm.explain",
            {
                "llm.trace_format": request.trace_format,
                "session.id": request.session_id,
            },
        ):
            explanation = orchestrator.generate_explanation(
                request.trace_content,
                request.trace_format,
                request.session_id,
            )
    except Exception:
        llm_call_total.labels(operation="explain", status="error").inc()
        raise
    llm_call_total.labels(operation="explain", status="success").inc()
    llm_response_length.observe(len(explanation))
    return ExplanationResponse(
        explanation=explanation,
        trace_format=request.trace_format,
    )


@router.post("/induce/start", response_model=InductionStatusResponse)
async def start_induction(request: InductionStartRequest) -> InductionStatusResponse:
    adapter = create_induction_adapter(
        FeatureFlags(induction_pipeline=request.enabled)
    )
    try:
        with reasoning_span(
            "induction.batch",
            {
                "induction.rule_name": request.rule_name,
                "induction.session_count": len(request.session_ids),
            },
        ):
            result = adapter.start_batch(request.session_ids, request.rule_name)
    except Exception:
        induction_total.labels(operation="start", status="error").inc()
        reasoning_route_total.labels(mode="INDUCTION", action="ERROR").inc()
        raise
    induction_total.labels(operation="start", status=result.get("status", "unknown")).inc()
    reasoning_route_total.labels(mode="INDUCTION", action="START_BATCH").inc()
    return InductionStatusResponse(**result)


@router.get("/induce/status/{job_id}", response_model=InductionStatusResponse)
async def induction_status(job_id: str) -> InductionStatusResponse:
    with reasoning_span("induction.status", {"induction.job_id": job_id}):
        result = CeleryInductionAdapter().get_status(job_id)
    induction_total.labels(operation="status", status=result.get("status", "unknown")).inc()
    return InductionStatusResponse(**result)


@router.post("/induce/promote", response_model=InductionStatusResponse)
async def promote_induction_candidate(request: PromotionRequest) -> InductionStatusResponse:
    with reasoning_span("induction.promote", {"induction.job_id": request.job_id}):
        result = CeleryInductionAdapter().promote(
            request.job_id,
            request.candidate_rule,
        )
    induction_total.labels(operation="promote", status=result.get("status", "unknown")).inc()
    return InductionStatusResponse(**result)

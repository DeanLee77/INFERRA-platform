"""
Inference API Router.
Handles inference session management and question/answer flow.

Phase 1 WS-5 enhancements:
- Iterate progress in /next-question
- Idempotency-Key support on /feed-answer (TTL + max-size + thread-safe)
- Pagination on /summary
- fact_source in summary items
"""

import json
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from src.adapters.inbound.http.dependencies import get_db_session
from src.adapters.outbound.persistence.rule_repository import RuleRepositoryImpl
from src.domain.fact_values import FactValue, FactValueType
from src.domain.inference.session import InferenceSession
from src.domain.inference.session_service import InferenceSessionService
from src.domain.nodes.iterate_line import IterateLine
from src.domain.nodes.line_type import LineType
from src.domain.session import InferenceContext
from src.domain.trace import ProvOTraceGenerator
from src.ports.session_store_port import SessionStorePort
from src.schemas.inference_schemas import (
    AnswerEntry,
    ResetAnswerRequest,
    EditAnswerResponse,
    ErrorResponse,
    FeedAnswerRequest,
    FeedAnswerResponse,
    IterateAnswerPayload,
    IterateProgress,
    MLSessionCreateRequest,
    NextQuestionResponse,
    QuestionItem,
    SessionCreateRequest,
    SessionCreateResponse,
    SummaryItem,
    SummaryResponse,
    TraceResponse,
    UpdateHistoryRequest,
    UpdateHistoryResponse,
)
from src.services.rule_service import RuleService
from src.dependencies import get_session_store, get_rule_repository

import structlog

router = APIRouter(prefix="/api/v1/inference", tags=["inference"])
logger = structlog.get_logger("inferra.fastapi.inference")


# =============================================================================
# Bounded idempotency store with TTL + LRU eviction + thread safety
# =============================================================================

class IdempotencyStore:
    """Thread-safe idempotency store with TTL expiry and LRU eviction."""

    DEFAULT_MAX_SIZE = 1000
    DEFAULT_TTL_SECONDS = 300

    def __init__(
        self,
        max_size: int = DEFAULT_MAX_SIZE,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ):
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._store: OrderedDict[str, Tuple[float, FeedAnswerResponse]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[FeedAnswerResponse]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            ts, response = entry
            if time.time() - ts >= self._ttl:
                del self._store[key]
                return None
            self._store.move_to_end(key)
            return response

    def put(self, key: str, response: FeedAnswerResponse) -> None:
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
                self._store[key] = (time.time(), response)
                return
            if len(self._store) >= self._max_size:
                self._store.popitem(last=False)
            self._store[key] = (time.time(), response)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


_idempotency_store = IdempotencyStore()


# =============================================================================
# Dependencies
# =============================================================================

def _rule_service(db=Depends(get_db_session)) -> RuleService:
    repo = get_rule_repository(db)
    return RuleService(repo)


def _session_service(
    session_store: SessionStorePort = Depends(get_session_store)
) -> InferenceSessionService:
    return InferenceSessionService(session_store)


def _get_session_or_404(
    session_id: str = Query(..., description="Session identifier"),
    session_service: InferenceSessionService = Depends(_session_service),
) -> InferenceSession:
    session = session_service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return session


def _session_context(session: InferenceSession) -> InferenceContext:
    existing = getattr(session, "context", None)
    if isinstance(existing, InferenceContext):
        return existing

    assessment_state = session.inference_engine.get_assessment_state()
    return InferenceContext(
        session_id=session.session_id,
        rule_name=session.rule_name,
        target=session.target_node_name,
        mandatory=list(assessment_state.get_mandatory_list()),
        fact_store=assessment_state.get_fact_store(),
    )


def _convergence_state(session: InferenceSession) -> str:
    assessment_state = session.inference_engine.get_assessment_state()
    working_memory = assessment_state.get_working_memory()
    goal_fact = working_memory.get(session.assessment.get_goal_node().get_node_name())
    if goal_fact is not None and assessment_state.all_mandatory_node_determined():
        return "GOAL_REACHED"
    if session.assessment.get_node_to_be_asked() is not None:
        return "AWAITING_INPUT"
    return "PENDING"


# =============================================================================
# Session Management Endpoints
# =============================================================================

def _create_session_impl(
    rule_name: str,
    target_node_name: str,
    use_history: bool,
    rule_service: RuleService,
    session_service: InferenceSessionService,
) -> SessionCreateResponse:
    try:
        session = session_service.create_session_from_rule(
            rule_name=rule_name,
            target_node_name=target_node_name,
            rule_service=rule_service,
            use_history=use_history,
        )
        return SessionCreateResponse(
            session_id=session.session_id,
            rule_name=session.rule_name,
            target_node_name=session.target_node_name,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/sessions",
    response_model=SessionCreateResponse,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
)
async def create_session(
    request: SessionCreateRequest,
    rule_service: RuleService = Depends(_rule_service),
    session_service: InferenceSessionService = Depends(_session_service),
) -> SessionCreateResponse:
    logger.info("creating_session", rule_name=request.rule_name, target_node_name=request.target_node_name, use_history=False)
    return _create_session_impl(request.rule_name, request.target_node_name, False, rule_service, session_service)


@router.post(
    "/sessions/ml",
    response_model=SessionCreateResponse,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
)
async def create_ml_session(
    request: MLSessionCreateRequest,
    rule_service: RuleService = Depends(_rule_service),
    session_service: InferenceSessionService = Depends(_session_service),
) -> SessionCreateResponse:
    logger.info("creating_ml_session", rule_name=request.rule_name, target_node_name=request.target_node_name, use_history=True)
    return _create_session_impl(request.rule_name, request.target_node_name, True, rule_service, session_service)


# =============================================================================
# Question/Answer Flow Endpoints
# =============================================================================

@router.get(
    "/next-question",
    response_model=NextQuestionResponse,
    responses={404: {"model": ErrorResponse}},
)
async def get_next_question(
    session_id: str = Query(..., description="Session identifier"),
    session: InferenceSession = Depends(_get_session_or_404),
) -> NextQuestionResponse:
    logger.info("getting_next_question", session_id=session_id)

    inference_engine = session.inference_engine
    assessment = session.assessment
    target_node_name = session.target_node_name

    next_question_node = inference_engine.get_next_question_with_goal_name(target_node_name)

    if next_question_node is None:
        return NextQuestionResponse(
            session_id=session_id,
            questions=[],
            has_more_questions=False,
            convergence_state=_convergence_state(session),
        )

    iterate_progress: Optional[IterateProgress] = None
    if assessment.get_node_to_be_asked() is not None and \
       assessment.get_node_to_be_asked().get_line_type() == LineType.ITERATE:
        assessment.set_aux_node_to_be_asked(next_question_node)
        iterate_node = assessment.get_node_to_be_asked()
        if isinstance(iterate_node, IterateLine):
            answered, total = iterate_node.get_progress()
            number_of_target_raw = iterate_node.get_number_of_target()
            list_name_raw = iterate_node.get_given_list_name()
            number_of_target = (
                number_of_target_raw
                if isinstance(number_of_target_raw, str) and number_of_target_raw
                else "ALL"
            )
            list_name = list_name_raw if isinstance(list_name_raw, str) else ""
            iterate_progress = IterateProgress(
                answered=answered,
                total=total,
                quantifier=number_of_target,
                list_name=list_name,
            )

    question_types = inference_engine.find_type_of_element_to_be_asked(next_question_node)
    questions = inference_engine.get_questions_from_node_to_be_asked(next_question_node)

    question_items = []
    for question in questions:
        question_type = question_types.get(question)
        question_items.append(QuestionItem(
            question_text=question,
            question_value_type=str(question_type.value).lower() if question_type else "unknown",
        ))

    working_memory = inference_engine.get_assessment_state().get_working_memory()
    goal_fact = working_memory.get(assessment.get_goal_node().get_node_name())
    has_more = goal_fact is None or not inference_engine.get_assessment_state().all_mandatory_node_determined()

    return NextQuestionResponse(
        session_id=session_id,
        questions=question_items,
        has_more_questions=has_more,
        iterate_progress=iterate_progress,
        convergence_state=_convergence_state(session),
    )


@router.post(
    "/feed-answer",
    response_model=FeedAnswerResponse,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def feed_answer(
    request: FeedAnswerRequest,
    fastapi_request: Request,
    session_id: str = Query(..., description="Session identifier"),
    session: InferenceSession = Depends(_get_session_or_404),
) -> FeedAnswerResponse:
    logger.info("feeding_answer", session_id=session_id, question=request.question)

    idempotency_key = fastapi_request.headers.get("Idempotency-Key")
    cache_key = f"{session_id}:{idempotency_key}" if idempotency_key else None

    if cache_key:
        cached_response = _idempotency_store.get(cache_key)
        if cached_response is not None:
            logger.info("idempotency_key_hit", session_id=session_id, idempotency_key=idempotency_key)
            return cached_response

    inference_engine = session.inference_engine
    assessment = session.assessment

    if not idempotency_key:
        working_memory = inference_engine.get_assessment_state().get_working_memory()
        node_name = assessment.get_node_to_be_asked().get_node_name() if assessment.get_node_to_be_asked() else None
        if node_name and node_name in working_memory:
            raise HTTPException(
                status_code=409,
                detail={
                    "error_code": "DUPLICATE_ANSWER",
                    "message": f"Answer already submitted for node '{node_name}'",
                },
            )

    try:
        fact_value_type = FactValueType[str(request.answer.type).upper()]
    except KeyError:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported answer type: {request.answer.type}",
        )

    active_question_node = assessment.get_node_to_be_asked()
    if active_question_node is None:
        raise HTTPException(status_code=400, detail="No active question is set for this assessment")

    if active_question_node.get_line_type() == LineType.ITERATE:
        active_node = assessment.get_aux_node_to_be_asked()
        if active_node is None:
            raise HTTPException(
                status_code=400,
                detail="Iterate node has no active sub-question set",
            )
        try:
            IterateAnswerPayload(
                question=request.question,
                answer=request.answer,
                index=1,
            )
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "INVALID_ITERATE_ANSWER",
                    "message": str(e),
                },
            )
    else:
        active_node = active_question_node

    inference_engine.feed_answer_to_node(
        active_node,
        request.question,
        str(request.answer.answer),
        fact_value_type,
        assessment,
    )

    working_memory = inference_engine.get_assessment_state().get_working_memory()
    goal_fact = working_memory.get(assessment.get_goal_node().get_node_name())

    if goal_fact is None or not inference_engine.get_assessment_state().all_mandatory_node_determined():
        response = FeedAnswerResponse(has_more_questions=True)
    else:
        goal_node_name = assessment.get_goal_node().get_node_name()
        goal_types = inference_engine.find_type_of_element_to_be_asked(assessment.get_goal_node())
        goal_type = goal_types.get(goal_node_name)

        response = FeedAnswerResponse(
            has_more_questions=False,
            goal_rule_name=goal_node_name,
            goal_rule_value=str(goal_fact.get_value()),
            goal_rule_type=str(goal_type.value).lower() if goal_type else "unknown",
        )

    if cache_key:
        _idempotency_store.put(cache_key, response)

    return response


@router.post(
    "/reset-answer",
    response_model=EditAnswerResponse,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
)
async def reset_answer(
    request: ResetAnswerRequest,
    session_id: str = Query(..., description="Session identifier"),
    session: InferenceSession = Depends(_get_session_or_404),
) -> EditAnswerResponse:
    logger.info("resetting_answer", session_id=session_id, question=request.question)

    inference_engine = session.inference_engine
    assessment = session.assessment

    inference_engine.edit_answer(request.question)

    working_memory = inference_engine.get_assessment_state().get_working_memory()
    goal_fact = working_memory.get(assessment.get_goal_node().get_node_name())

    if goal_fact is None or not inference_engine.get_assessment_state().all_mandatory_node_determined():
        return EditAnswerResponse(has_more_questions=True)

    goal_node_name = assessment.get_goal_node().get_node_name()
    goal_types = inference_engine.find_type_of_element_to_be_asked(assessment.get_goal_node())
    goal_type = goal_types.get(goal_node_name)

    return EditAnswerResponse(
        has_more_questions=False,
        goal_rule_name=goal_node_name,
        goal_rule_value=str(goal_fact.get_value()),
        goal_rule_type=str(goal_type.value).lower() if goal_type else "unknown",
    )


# =============================================================================
# Summary Endpoint
# =============================================================================

@router.get(
    "/summary",
    response_model=SummaryResponse,
    responses={404: {"model": ErrorResponse}},
)
async def get_summary(
    session_id: str = Query(..., description="Session identifier"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(0, ge=0, description="Max items to return (0 = all)"),
    session: InferenceSession = Depends(_get_session_or_404),
) -> SummaryResponse:
    logger.info("getting_summary", session_id=session_id, offset=offset, limit=limit)

    inference_engine = session.inference_engine
    assessment_state = inference_engine.get_assessment_state()
    working_memory = assessment_state.get_working_memory()
    summary_list = assessment_state.get_summary_list()

    fact_sources_map: Dict[str, str] = {}
    try:
        from src.domain.state.fact_source import FactSource
        for name in working_memory:
            sources = assessment_state.get_fact_store().get_fact_sources(name)
            if sources:
                if FactSource.ASSERTED in sources:
                    fact_sources_map[name] = FactSource.ASSERTED.value
                elif FactSource.INFERRED in sources:
                    fact_sources_map[name] = FactSource.INFERRED.value
                elif FactSource.LEARNED in sources:
                    fact_sources_map[name] = FactSource.LEARNED.value
                elif FactSource.HYPOTHETICAL in sources:
                    fact_sources_map[name] = FactSource.HYPOTHETICAL.value
                elif FactSource.SEMANTIC in sources:
                    fact_sources_map[name] = FactSource.SEMANTIC.value
    except Exception:
        logger.warning("fact_source_lookup_failed", session_id=session_id, exc_info=True)

    summary_items = []

    for summary_item in summary_list:
        fact_value = working_memory.get(summary_item)
        if fact_value is None:
            continue
        summary_items.append(SummaryItem(
            node_text=summary_item,
            node_value=str(fact_value.get_value()),
            fact_source=fact_sources_map.get(summary_item),
        ))

    for key, fact_value in working_memory.items():
        if key not in summary_list:
            if isinstance(fact_value.get_value(), list):
                value = json.dumps([fv.get_value() for fv in fact_value.get_value()])
            else:
                value = str(fact_value.get_value())
            summary_items.append(SummaryItem(
                node_text=key,
                node_value=value,
                fact_source=fact_sources_map.get(key),
            ))

    total_count = len(summary_items)
    if limit > 0:
        paginated = summary_items[offset:offset + limit]
    else:
        paginated = summary_items[offset:]

    ctx = _session_context(session)
    return SummaryResponse(
        session_id=session_id,
        summary=paginated,
        total_count=total_count,
        offset=offset,
        limit=limit,
        reasoning_mode=ctx.reasoning_mode,
        confidence=ctx.confidence,
        status=_convergence_state(session),
        origin_job_id=ctx.induction_job_id,
    )


@router.get(
    "/trace",
    response_model=TraceResponse,
    responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
async def get_trace(
    session_id: str = Query(..., description="Session identifier"),
    trace_format: str = Query(
        "turtle",
        alias="format",
        description="Trace serialization format (turtle or json-ld)",
        pattern="^(turtle|json-ld|jsonld)$",
    ),
    session: InferenceSession = Depends(_get_session_or_404),
) -> TraceResponse:
    logger.info("getting_trace", session_id=session_id, trace_format=trace_format)
    ctx = _session_context(session)
    normalized_format = "json-ld" if trace_format == "jsonld" else trace_format
    try:
        trace = ProvOTraceGenerator().generate(ctx, output_format=normalized_format)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return TraceResponse(
        session_id=session_id,
        format=normalized_format,
        trace=trace,
        reasoning_mode=ctx.reasoning_mode,
        confidence=ctx.confidence,
    )


# =============================================================================
# History Update Endpoint
# =============================================================================

@router.post(
    "/history",
    response_model=UpdateHistoryResponse,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
)
async def update_history(
    request: UpdateHistoryRequest,
    session_id: str = Query(..., description="Session identifier"),
    session: InferenceSession = Depends(_get_session_or_404),
    rule_service: RuleService = Depends(_rule_service),
) -> UpdateHistoryResponse:
    logger.info("updating_history", session_id=session_id, rule_name=request.rule_name)

    inference_engine = session.inference_engine
    working_memory = inference_engine.get_assessment_state().get_working_memory()

    try:
        rule_service.save_session_history(request.rule_name, working_memory)
    except LookupError:
        raise HTTPException(status_code=404, detail=f"Rule '{request.rule_name}' not found")

    return UpdateHistoryResponse(updated=True)

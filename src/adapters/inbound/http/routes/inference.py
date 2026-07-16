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
import re
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, List, Mapping, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session as DbSession

from src.adapters.inbound.http.dependencies import get_db_session, require_scope
from src.adapters.outbound.persistence.llm_product_configuration_repository import (
    LLMProductConfigurationRepository,
)
from src.adapters.outbound.ontology.fuseki_adapter import FusekiAdapter
from src.adapters.outbound.persistence.rule_repository import RuleRepositoryImpl
from src.domain.exceptions import ConcurrentModificationError
from src.domain.fact_values import FactValue, FactValueType
from src.domain.inference.session import InferenceSession
from src.domain.inference.session_service import InferenceSessionService
from src.domain.nodes.iterate_line import IterateLine
from src.domain.nodes.line_type import LineType
from src.domain.session import InferenceContext
from src.domain.state import FactSource
from src.domain.state.feature_flags import (
    FeatureFlags,
    ONTOLOGY_ASSISTANCE_PROFILES,
    get_feature_flags,
    normalize_ontology_profile,
)
from src.domain.trace import ProvOTraceGenerator
from src.tasks.ontology_post_reasoner import run_post_reasoning
from src.ports.session_store_port import SessionStorePort
from src.services.ontology_artifact_service import (
    build_case_run_ontology_artifact,
    facts_from_assessment_state,
)
from src.adapters.inbound.http.schemas.inference import (
    AnswerEntry,
    DeferQuestionRequest,
    DeferQuestionResponse,
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
    QuestionOption,
    SessionDeleteResponse,
    SessionListItem,
    SessionListResponse,
    SessionCreateRequest,
    SessionCreateResponse,
    SummaryItem,
    SummaryResponse,
    TraceResponse,
    UpdateHistoryRequest,
    UpdateHistoryResponse,
)
from src.adapters.inbound.http.schemas.ontology_artifacts import (
    CaseRunSyncRequest,
    CaseRunSyncResponse,
    CaseRunCollisionCheckResponse,
    OntologyArtifactResponse,
)
from src.services.rule_service import RuleService
from src.adapters.inbound.http.dependencies import get_session_store, get_rule_repository
from src.services.llm_configuration_service import LLMConfigurationService
from src.services.inference_orchestration_service import (
    get_inference_orchestration_service,
)

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
    request: Request,
    session_id: str = Query(..., description="Session identifier"),
    session_service: InferenceSessionService = Depends(_session_service),
) -> InferenceSession:
    session = session_service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    _enforce_session_owner(session, request)
    return session


def _request_user_id(request: Request) -> Optional[str]:
    user_id = request.scope.get("inferra_user_id")
    return str(user_id) if user_id else None


def _llm_configuration_snapshot(product_id: str, db: DbSession) -> dict[str, Any]:
    return LLMConfigurationService(LLMProductConfigurationRepository(db)).snapshot_for_product(
        product_id
    )


def _enforce_session_owner(session: InferenceSession, request: Request) -> None:
    if not get_feature_flags().auth_enabled:
        return
    requester = _request_user_id(request)
    if not requester:
        raise HTTPException(status_code=401, detail="Authenticated user identity is missing")
    if session.owner_id is not None and session.owner_id != requester:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "SESSION_OWNER_MISMATCH",
                "message": "Session belongs to a different authenticated principal",
            },
        )


def _can_access_session(session: InferenceSession, request: Request) -> bool:
    if not get_feature_flags().auth_enabled:
        return True
    requester = _request_user_id(request)
    if not requester:
        raise HTTPException(status_code=401, detail="Authenticated user identity is missing")
    return session.owner_id is None or session.owner_id == requester


def _save_session_or_409(
    session_service: InferenceSessionService,
    session: InferenceSession,
) -> None:
    if not isinstance(session_service, InferenceSessionService) or not hasattr(session_service, "_store"):
        return
    try:
        session_service.save_session(session)
    except ConcurrentModificationError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "SESSION_CONFLICT",
                "message": str(exc),
            },
        ) from exc


def _session_context(session: InferenceSession) -> InferenceContext:
    existing = getattr(session, "context", None)
    if isinstance(existing, InferenceContext):
        return _refresh_session_context(session, existing)

    assessment_state = session.inference_engine.get_assessment_state()
    return _refresh_session_context(session, InferenceContext(
        session_id=session.session_id,
        rule_name=session.rule_name,
        target=session.target_node_name,
        mandatory=list(assessment_state.get_mandatory_list()),
        fact_store=assessment_state.get_fact_store(),
        ontology_profile=getattr(session, "ontology_profile", "custom"),
        ontology_profile_source=getattr(session, "ontology_profile_source", "environment"),
        ontology_flags=(
            session.feature_flags.snapshot()
            if getattr(session, "feature_flags", None) is not None
            else {}
        ),
    ))


def _session_feature_flags(session: InferenceSession) -> FeatureFlags:
    """Return the frozen session snapshot, with a legacy-session fallback."""
    return session.feature_flags or get_feature_flags()


def _enriched_question_suggestions(
    context: Optional[InferenceContext],
    question: str,
) -> List[Dict[str, Any]]:
    if context is None:
        return []
    suggestions: List[Dict[str, Any]] = []
    for mapping in (
        context.ontology_advisory_suggestions,
        context.ontology_value_suggestions,
        context.ontology_constraint_suggestions,
    ):
        suggestions.extend(dict(item) for item in mapping.get(question, ()))
    return suggestions


def _refresh_session_context(
    session: InferenceSession,
    ctx: InferenceContext,
) -> InferenceContext:
    inference_engine = session.inference_engine
    ctx.ontology_profile = getattr(session, "ontology_profile", ctx.ontology_profile)
    ctx.ontology_profile_source = getattr(
        session,
        "ontology_profile_source",
        ctx.ontology_profile_source,
    )
    if getattr(session, "feature_flags", None) is not None and not ctx.ontology_flags:
        ctx.ontology_flags = session.feature_flags.snapshot()

    auto_answer_trace = getattr(inference_engine, "get_ontology_auto_answer_trace", None)
    materialization_trace = getattr(inference_engine, "get_ontology_materialization_trace", None)
    derived_facts = getattr(inference_engine, "get_ontology_derived_facts", None)
    question_strategy_trace = getattr(
        inference_engine,
        "get_semantic_question_strategy_trace",
        None,
    )
    deferred_questions = getattr(inference_engine, "get_deferred_questions", None)
    if callable(auto_answer_trace):
        ctx.ontology_auto_answer_trace = auto_answer_trace()
    if callable(materialization_trace):
        ctx.ontology_materialization_trace = materialization_trace()
        ctx.ontology_reasoning_applied = bool(ctx.ontology_materialization_trace)
    if callable(derived_facts):
        ctx.ontology_derived_facts = derived_facts()
    if callable(question_strategy_trace):
        ctx.semantic_question_strategy_trace = question_strategy_trace()
        ctx.semantic_questions_skipped = [
            item
            for item in ctx.semantic_question_strategy_trace
            if item.get("action") in {"pruned", "deferred"}
        ]
    if callable(deferred_questions):
        existing = {
            str(item.get("question") or item.get("questionName") or "")
            for item in ctx.deferred_semantic_questions
        }
        for question_name in deferred_questions():
            if question_name and question_name not in existing:
                ctx.deferred_semantic_questions.append({
                    "question": question_name,
                    "node_name": question_name,
                    "reason": "deferred_during_full_semantic_generation",
                    "deferred_during": "FULL_SEMANTIC_TTL_GENERATION",
                })
                existing.add(question_name)
    return ctx


def _convergence_state(session: InferenceSession) -> str:
    assessment_state = session.inference_engine.get_assessment_state()
    working_memory = assessment_state.get_working_memory()
    goal_fact = working_memory.get(session.assessment.get_goal_node().get_node_name())
    if goal_fact is not None and assessment_state.all_mandatory_node_determined():
        return "GOAL_REACHED"
    if session.assessment.get_node_to_be_asked() is not None:
        return "AWAITING_INPUT"
    return "PENDING"


def _session_goal_decision(session: InferenceSession) -> Tuple[str, Optional[str]]:
    goal_node = session.assessment.get_goal_node()
    goal_name = goal_node.get_node_name() if goal_node is not None else session.target_node_name
    goal_fact = session.inference_engine.get_assessment_state().get_working_memory().get(goal_name)
    if goal_fact is None:
        return goal_name, None
    value = goal_fact.get_value() if hasattr(goal_fact, "get_value") else goal_fact
    return goal_name, None if value is None else str(value)


def _normalized_decision_value(value: Optional[str]) -> str:
    return str(value).strip().lower() if value is not None else ""


def _apply_original_decision_context(
    session: InferenceSession,
    request: CaseRunSyncRequest,
) -> None:
    if request.original_decision_name is None and request.original_decision_value is None:
        return

    ctx = _session_context(session)
    semantic_decision_name, semantic_decision_value = _session_goal_decision(session)
    ctx.decision_locked = True
    ctx.original_decision_name = (
        str(request.original_decision_name)
        if request.original_decision_name is not None
        else ctx.original_decision_name
    )
    ctx.original_decision_value = (
        str(request.original_decision_value)
        if request.original_decision_value is not None
        else ctx.original_decision_value
    )

    if (
        ctx.original_decision_value is not None
        and semantic_decision_value is not None
        and _normalized_decision_value(ctx.original_decision_value)
        != _normalized_decision_value(semantic_decision_value)
    ):
        ctx.semantic_divergence = {
            "original_decision_name": ctx.original_decision_name,
            "original_decision_value": ctx.original_decision_value,
            "semantic_decision_name": semantic_decision_name,
            "semantic_decision_value": semantic_decision_value,
            "reason": (
                "Full semantic completion produced a different target value than "
                "the locked original case execution decision."
            ),
        }
    else:
        ctx.semantic_divergence = None


def _fact_value_type_text(fact_value: Any) -> str:
    value_type = fact_value.get_value_type() if hasattr(fact_value, "get_value_type") else None
    return str(value_type.value).lower() if isinstance(value_type, FactValueType) else "string"


def _fact_value_to_option(fact_value: Any) -> QuestionOption:
    value = fact_value.get_value() if hasattr(fact_value, "get_value") else fact_value
    return QuestionOption(
        label=str(value),
        value=value,
        value_type=_fact_value_type_text(fact_value),
    )


def _options_from_declaration(declaration: Any) -> List[QuestionOption]:
    if not hasattr(declaration, "get_value_type") or declaration.get_value_type() != FactValueType.LIST:
        return []

    values = declaration.get_value() if hasattr(declaration, "get_value") else None
    if not isinstance(values, list):
        return []

    return [_fact_value_to_option(value) for value in values]


def _question_name_candidates(question: str, declarations: Dict[str, Any]) -> List[str]:
    candidates = {question}
    for declared_name in declarations:
        if question.endswith(f"  {declared_name}") or question.endswith(f".{declared_name}"):
            candidates.add(declared_name)
    return sorted(candidates, key=len, reverse=True)


def _list_options_for_question(inference_engine: Any, question: str, question_type: Optional[FactValueType]) -> List[QuestionOption]:
    if question_type != FactValueType.LIST:
        return []

    node_set = inference_engine.get_node_set() if hasattr(inference_engine, "get_node_set") else None
    if node_set is None:
        return []

    input_declarations = node_set.get_input_dictionary()
    fixed_declarations = node_set.get_fact_dictionary()
    for candidate in _question_name_candidates(question, input_declarations):
        options = _options_from_declaration(input_declarations.get(candidate))
        if options:
            return options

    for candidate in _question_name_candidates(question, fixed_declarations):
        options = _options_from_declaration(fixed_declarations.get(candidate))
        if options:
            return options

    return []


def _timestamp_text(value: Any) -> Optional[str]:
    return value.isoformat() if hasattr(value, "isoformat") else None


def _session_list_item(session: InferenceSession) -> SessionListItem:
    return SessionListItem(
        session_id=session.session_id,
        rule_name=session.rule_name,
        target_node_name=session.target_node_name,
        created_at=_timestamp_text(getattr(session, "created_at", None)),
        last_accessed=_timestamp_text(getattr(session, "last_accessed", None)),
    )


# =============================================================================
# Session Management Endpoints
# =============================================================================

def _create_session_impl(
    rule_name: str,
    target_node_name: str,
    use_history: bool,
    rule_service: RuleService,
    session_service: InferenceSessionService,
    owner_id: Optional[str] = None,
    ontology_profile: Optional[str] = None,
    ontology_flags: Optional[Mapping[str, Any]] = None,
    llm_configuration_snapshot: Optional[Mapping[str, Any]] = None,
) -> SessionCreateResponse:
    try:
        session = session_service.create_session_from_rule(
            rule_name=rule_name,
            target_node_name=target_node_name,
            rule_service=rule_service,
            use_history=use_history,
            owner_id=owner_id,
            ontology_profile=ontology_profile,
            ontology_flags=ontology_flags,
            llm_configuration=llm_configuration_snapshot,
        )
        return SessionCreateResponse(
            session_id=session.session_id,
            rule_name=session.rule_name,
            target_node_name=session.target_node_name,
            ontology_profile=session.ontology_profile,
            llm_configuration=session.llm_configuration,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/sessions",
    response_model=SessionListResponse,
)
async def list_sessions(
    fastapi_request: Request,
    session_service: InferenceSessionService = Depends(_session_service),
) -> SessionListResponse:
    sessions = [
        _session_list_item(session)
        for session in session_service.list_sessions()
        if _can_access_session(session, fastapi_request)
    ]
    return SessionListResponse(sessions=sessions, total_count=len(sessions))


@router.post(
    "/sessions",
    response_model=SessionCreateResponse,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
    dependencies=[Depends(require_scope("inference:write"))],
)
async def create_session(
    request: SessionCreateRequest,
    fastapi_request: Request,
    rule_service: RuleService = Depends(_rule_service),
    session_service: InferenceSessionService = Depends(_session_service),
) -> SessionCreateResponse:
    logger.info(
        "creating_session",
        rule_name=request.rule_name,
        target_node_name=request.target_node_name,
        use_history=True,
    )
    return _create_session_impl(
        rule_name=request.rule_name,
        target_node_name=request.target_node_name,
        use_history=True,
        rule_service=rule_service,
        session_service=session_service,
        owner_id=_request_user_id(fastapi_request),
        ontology_profile=request.ontology_profile,
        ontology_flags=request.ontology_flags,
    )


@router.delete(
    "/sessions/{session_id}",
    response_model=SessionDeleteResponse,
    dependencies=[Depends(require_scope("inference:write"))],
)
async def delete_session(
    session_id: str,
    fastapi_request: Request,
    session_service: InferenceSessionService = Depends(_session_service),
) -> SessionDeleteResponse:
    session = session_service.get_session(session_id)
    if session is not None:
        _enforce_session_owner(session, fastapi_request)
    return SessionDeleteResponse(
        session_id=session_id,
        deleted=session_service.delete_session(session_id),
    )


@router.post(
    "/sessions/ml",
    response_model=SessionCreateResponse,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
    dependencies=[Depends(require_scope("inference:write"))],
)
async def create_ml_session(
    request: MLSessionCreateRequest,
    fastapi_request: Request,
    rule_service: RuleService = Depends(_rule_service),
    session_service: InferenceSessionService = Depends(_session_service),
) -> SessionCreateResponse:
    logger.info("creating_ml_session", rule_name=request.rule_name, target_node_name=request.target_node_name, use_history=True)
    return _create_session_impl(
        rule_name=request.rule_name,
        target_node_name=request.target_node_name,
        use_history=True,
        rule_service=rule_service,
        session_service=session_service,
        owner_id=_request_user_id(fastapi_request),
        ontology_profile=request.ontology_profile,
        ontology_flags=request.ontology_flags,
    )


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
    session_service: InferenceSessionService = Depends(_session_service),
) -> NextQuestionResponse:
    logger.info("getting_next_question", session_id=session_id)

    inference_engine = session.inference_engine
    assessment = session.assessment
    target_node_name = session.target_node_name

    next_question_node = inference_engine.get_next_question_with_goal_name(target_node_name)

    if next_question_node is None:
        convergence_state = _convergence_state(session)
        if convergence_state != "GOAL_REACHED":
            try:
                result = (
                    await get_inference_orchestration_service()
                    .evaluate_stalled_session(session)
                )
                if result.reason != "PENDING":
                    convergence_state = result.reason
                else:
                    convergence_state = _convergence_state(session)
            except Exception:
                logger.exception(
                    "stalled_session_orchestration_failed",
                    session_id=session_id,
                )
        _save_session_or_409(session_service, session)
        goal_reached = convergence_state == "GOAL_REACHED"
        return NextQuestionResponse(
            session_id=session_id,
            questions=[],
            has_more_questions=False,
            convergence_state=convergence_state,
            question_flow_state=(
                "GOAL_REACHED" if goal_reached else "BLOCKED_INCONSISTENT_STATE"
            ),
            blocked_reason=None if goal_reached else "NO_ASKABLE_QUESTION",
            blocked_detail=(
                None
                if goal_reached
                else "The goal is unresolved, but no askable question remains."
            ),
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
    flags = _session_feature_flags(session)
    enriched_context = _session_context(session) if flags.enriched_api else None

    question_items = []
    for question in questions:
        question_type = question_types.get(question)
        options = _list_options_for_question(inference_engine, question, question_type)
        question_items.append(QuestionItem(
            question_text=question,
            question_value_type=str(question_type.value).lower() if question_type else "unknown",
            control="select" if options else None,
            options=options,
            selection_mode="single" if options else None,
            semantic_suggestions=_enriched_question_suggestions(
                enriched_context,
                question,
            ),
        ))

    working_memory = inference_engine.get_assessment_state().get_working_memory()
    goal_fact = working_memory.get(assessment.get_goal_node().get_node_name())
    has_more = goal_fact is None or not inference_engine.get_assessment_state().all_mandatory_node_determined()

    response = NextQuestionResponse(
        session_id=session_id,
        questions=question_items,
        has_more_questions=has_more,
        iterate_progress=iterate_progress,
        convergence_state=_convergence_state(session),
    )
    _save_session_or_409(session_service, session)
    return response


@router.post(
    "/feed-answer",
    response_model=FeedAnswerResponse,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    dependencies=[Depends(require_scope("inference:write"))],
)
async def feed_answer(
    request: FeedAnswerRequest,
    fastapi_request: Request,
    session_id: str = Query(..., description="Session identifier"),
    session: InferenceSession = Depends(_get_session_or_404),
    session_service: InferenceSessionService = Depends(_session_service),
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

    if not idempotency_key:
        working_memory = inference_engine.get_assessment_state().get_working_memory()
        question_keys = [request.question]
        try:
            question_keys.extend(inference_engine.get_questions_from_node_to_be_asked(active_node))
        except Exception:
            logger.warning("question_key_lookup_failed", session_id=session_id, exc_info=True)

        duplicate_key = next(
            (
                question_key
                for question_key in dict.fromkeys(question_keys)
                if question_key and question_key in working_memory
            ),
            None,
        )
        if duplicate_key is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "error_code": "DUPLICATE_ANSWER",
                    "message": f"Answer already submitted for question '{duplicate_key}'",
                    "question": duplicate_key,
                },
            )

    inference_engine.feed_answer_to_node(
        active_node,
        request.question,
        request.answer.answer,
        fact_value_type,
        assessment,
    )
    if str(request.answer_context or "").upper() == "FULL_SEMANTIC_COMPLETION":
        ctx = _session_context(session)
        if request.question not in ctx.post_decision_answer_names:
            ctx.post_decision_answer_names.append(request.question)
        ctx.semantic_completion_policy = "INTERACTIVE_WITH_DEFERRED_ALLOWED"
        ctx.semantic_completion_status = "IN_PROGRESS"

    working_memory = inference_engine.get_assessment_state().get_working_memory()
    goal_fact = working_memory.get(assessment.get_goal_node().get_node_name())

    if goal_fact is None or not inference_engine.get_assessment_state().all_mandatory_node_determined():
        response = FeedAnswerResponse(has_more_questions=True)
    else:
        goal_node_name = assessment.get_goal_node().get_node_name()
        goal_types = inference_engine.find_type_of_element_to_be_asked(assessment.get_goal_node())
        goal_type = goal_types.get(goal_node_name)
        ctx = _session_context(session)
        ctx.decision_locked = True
        ctx.original_decision_name = ctx.original_decision_name or goal_node_name
        ctx.original_decision_value = ctx.original_decision_value or str(goal_fact.get_value())
        if ctx.deferred_semantic_questions:
            ctx.semantic_completion_status = "PARTIAL"
        elif ctx.ontology_profile == "full_semantic_pilot":
            ctx.semantic_completion_status = "COMPLETE"
            if ctx.semantic_completion_policy == "UNSPECIFIED":
                ctx.semantic_completion_policy = "INTERACTIVE_WITH_DEFERRED_ALLOWED"

        response = FeedAnswerResponse(
            has_more_questions=False,
            goal_rule_name=goal_node_name,
            goal_rule_value=str(goal_fact.get_value()),
            goal_rule_type=str(goal_type.value).lower() if goal_type else "unknown",
        )

    _save_session_or_409(session_service, session)
    if not response.has_more_questions:
        _run_ontology_post_reasoning(
            session_id=session_id,
            rule_name=session.rule_name,
            assessment_state=inference_engine.get_assessment_state(),
            feature_flags=session.feature_flags or get_feature_flags(),
        )
    if cache_key:
        _idempotency_store.put(cache_key, response)
    return response


@router.post(
    "/defer-question",
    response_model=DeferQuestionResponse,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    dependencies=[Depends(require_scope("inference:write"))],
)
async def defer_question(
    request: DeferQuestionRequest,
    session_id: str = Query(..., description="Session identifier"),
    session: InferenceSession = Depends(_get_session_or_404),
    session_service: InferenceSessionService = Depends(_session_service),
) -> DeferQuestionResponse:
    """Defer one semantic-completion question without asserting a fact value."""
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be blank")

    inference_engine = session.inference_engine
    assessment = session.assessment
    active_question_node = assessment.get_node_to_be_asked()
    active_node = assessment.get_aux_node_to_be_asked() or active_question_node
    if active_node is None:
        raise HTTPException(status_code=400, detail="No active question is set for this assessment")

    try:
        question_keys = set(inference_engine.get_questions_from_node_to_be_asked(active_node))
    except Exception:
        question_keys = set()
    question_keys.add(active_node.get_node_name())
    variable_name = active_node.get_variable_name()
    if isinstance(variable_name, str):
        question_keys.add(variable_name)
    if question not in question_keys:
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "QUESTION_NOT_ACTIVE",
                "message": f"Question '{question}' is not the active semantic-completion question",
                "active_questions": sorted(item for item in question_keys if item),
            },
        )

    inference_engine.defer_question(question)
    ctx = _session_context(session)
    ctx.semantic_completion_policy = (
        "DEFER_ALL_REMAINING"
        if request.defer_all_remaining
        else "INTERACTIVE_WITH_DEFERRED_ALLOWED"
    )
    ctx.semantic_completion_status = "PARTIAL"
    existing = {
        str(item.get("question") or item.get("questionName") or "")
        for item in ctx.deferred_semantic_questions
    }
    if question not in existing:
        ctx.deferred_semantic_questions.append({
            "question": question,
            "node_name": request.node_name or active_node.get_node_name(),
            "reason": request.reason or "user_deferred",
            "deferred_during": "FULL_SEMANTIC_TTL_GENERATION",
            "defer_all_remaining": request.defer_all_remaining,
        })

    _save_session_or_409(session_service, session)
    return DeferQuestionResponse(
        deferred=True,
        session_id=session_id,
        question=question,
        deferred_count=len(ctx.deferred_semantic_questions),
        defer_all_remaining=request.defer_all_remaining,
    )


def _run_ontology_post_reasoning(
    session_id: str,
    rule_name: str,
    assessment_state: Any,
    feature_flags: FeatureFlags,
) -> Optional[Dict[str, str]]:
    fact_store = assessment_state.get_fact_store()
    concluded_facts = []
    for source in (FactSource.INFERRED, FactSource.LEARNED, FactSource.HYPOTHETICAL):
        for name, fact_value in fact_store.get_layer_snapshot(source).items():
            concluded_facts.append({"name": name, "value": fact_value})
    if not concluded_facts:
        return None
    try:
        return run_post_reasoning(
            session_id=session_id,
            rule_name=rule_name,
            concluded_facts=concluded_facts,
            feature_flags=feature_flags,
        )
    except Exception:
        logger.exception(
            "ontology_post_reasoning_publish_failed",
            session_id=session_id,
            rule_name=rule_name,
        )
        return None


@router.post(
    "/reset-answer",
    response_model=EditAnswerResponse,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
    dependencies=[Depends(require_scope("inference:write"))],
)
async def reset_answer(
    request: ResetAnswerRequest,
    session_id: str = Query(..., description="Session identifier"),
    session: InferenceSession = Depends(_get_session_or_404),
    session_service: InferenceSessionService = Depends(_session_service),
) -> EditAnswerResponse:
    logger.info("resetting_answer", session_id=session_id, question=request.question)

    inference_engine = session.inference_engine
    assessment = session.assessment

    try:
        inference_engine.edit_answer(request.question)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    working_memory = inference_engine.get_assessment_state().get_working_memory()
    goal_fact = working_memory.get(assessment.get_goal_node().get_node_name())

    if goal_fact is None or not inference_engine.get_assessment_state().all_mandatory_node_determined():
        response = EditAnswerResponse(has_more_questions=True)
        _save_session_or_409(session_service, session)
        return response

    goal_node_name = assessment.get_goal_node().get_node_name()
    goal_types = inference_engine.find_type_of_element_to_be_asked(assessment.get_goal_node())
    goal_type = goal_types.get(goal_node_name)

    response = EditAnswerResponse(
        has_more_questions=False,
        goal_rule_name=goal_node_name,
        goal_rule_value=str(goal_fact.get_value()),
        goal_rule_type=str(goal_type.value).lower() if goal_type else "unknown",
    )
    _save_session_or_409(session_service, session)
    return response


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
    flags = _session_feature_flags(session)

    fact_sources_map: Dict[str, str] = {}
    if flags.enriched_api:
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
            logger.warning(
                "fact_source_lookup_failed",
                session_id=session_id,
                exc_info=True,
            )

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

    ctx = _session_context(session) if flags.enriched_api else None
    return SummaryResponse(
        session_id=session_id,
        summary=paginated,
        total_count=total_count,
        offset=offset,
        limit=limit,
        reasoning_mode=ctx.reasoning_mode if ctx is not None else "DEDUCTION",
        confidence=ctx.confidence if ctx is not None else 1.0,
        status=_convergence_state(session),
        origin_job_id=ctx.induction_job_id if ctx is not None else None,
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
    flags = _session_feature_flags(session)
    if not flags.prov_o_trace:
        raise HTTPException(
            status_code=503,
            detail="PROV-O trace generation is disabled for this session",
        )
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
        reasoning_mode=ctx.reasoning_mode if flags.enriched_api else "DEDUCTION",
        confidence=ctx.confidence if flags.enriched_api else 1.0,
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


# =============================================================================
# Case-Run Ontology Sync Endpoint
# =============================================================================

def _build_case_run_artifact_for_session(
    *,
    session_id: str,
    session: InferenceSession,
    rule_service: RuleService,
    case_name: Optional[str] = None,
    ontology_profile_override: Optional[str] = None,
):
    ctx = _session_context(session)
    rule_ontology = rule_service.get_rule_ontology_data(session.rule_name)
    assessment_state = session.inference_engine.get_assessment_state()
    ontology_profile = ctx.ontology_profile
    ontology_profile_source = ctx.ontology_profile_source
    ontology_flags = ctx.ontology_flags
    if ontology_profile_override:
        try:
            ontology_profile = normalize_ontology_profile(ontology_profile_override) or ctx.ontology_profile
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        ontology_profile_source = "export_override"
        ontology_flags = dict(ONTOLOGY_ASSISTANCE_PROFILES.get(ontology_profile, ctx.ontology_flags))
    return build_case_run_ontology_artifact(
        rule_ontology=rule_ontology,
        session_id=session_id,
        case_name=case_name,
        target_node_name=session.target_node_name,
        facts=facts_from_assessment_state(assessment_state),
        reasoning_mode=ctx.reasoning_mode,
        confidence=ctx.confidence,
        status=_convergence_state(session),
        ontology_profile=ontology_profile,
        ontology_profile_source=ontology_profile_source,
        ontology_flags=ontology_flags,
        ontology_auto_answer_trace=ctx.ontology_auto_answer_trace,
        ontology_materialization_trace=ctx.ontology_materialization_trace,
        semantic_question_strategy_trace=ctx.semantic_question_strategy_trace,
        ontology_derived_facts=ctx.ontology_derived_facts,
        deferred_questions=ctx.deferred_semantic_questions,
        post_decision_answer_names=ctx.post_decision_answer_names,
        semantic_completion_status=(
            ctx.semantic_completion_status
            if ctx.semantic_completion_status != "NOT_STARTED"
            else None
        ),
        semantic_completion_policy=ctx.semantic_completion_policy,
        decision_locked=ctx.decision_locked,
        original_decision_name=ctx.original_decision_name,
        original_decision_value=ctx.original_decision_value,
        semantic_divergence=ctx.semantic_divergence,
    )


@router.get(
    "/ontology-artifact",
    response_model=OntologyArtifactResponse,
    responses={404: {"model": ErrorResponse}},
)
async def get_case_run_ontology_artifact(
    session_id: str = Query(..., description="Session identifier"),
    case_name: Optional[str] = Query(None, description="Optional human-readable case name"),
    ontology_profile: Optional[str] = Query(
        None,
        description="Optional export-only ontology profile override, e.g. full_semantic_pilot",
    ),
    session: InferenceSession = Depends(_get_session_or_404),
    rule_service: RuleService = Depends(_rule_service),
) -> OntologyArtifactResponse:
    """Return a generated full case-run ontology artifact for the live session."""
    artifact = _build_case_run_artifact_for_session(
        session_id=session_id,
        session=session,
        rule_service=rule_service,
        case_name=case_name,
        ontology_profile_override=ontology_profile,
    )
    return OntologyArtifactResponse.model_validate(artifact.response_dict())


@router.get(
    "/ontology-artifact/download",
    responses={404: {"model": ErrorResponse}},
)
async def download_case_run_ontology_artifact(
    session_id: str = Query(..., description="Session identifier"),
    case_name: Optional[str] = Query(None, description="Optional human-readable case name"),
    ontology_profile: Optional[str] = Query(
        None,
        description="Optional export-only ontology profile override, e.g. full_semantic_pilot",
    ),
    session: InferenceSession = Depends(_get_session_or_404),
    rule_service: RuleService = Depends(_rule_service),
) -> Response:
    """Download a generated full case-run ontology artifact as Turtle."""
    artifact = _build_case_run_artifact_for_session(
        session_id=session_id,
        session=session,
        rule_service=rule_service,
        case_name=case_name,
        ontology_profile_override=ontology_profile,
    )
    return Response(
        content=artifact.turtle,
        media_type="text/turtle; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{artifact.artifact_name}"'
        },
    )


@router.get(
    "/ontology-artifact/collision-check",
    response_model=CaseRunCollisionCheckResponse,
    responses={400: {"model": ErrorResponse}},
)
async def check_case_run_collision(
    rule_name: str = Query(..., description="Rule name for the artifact stem"),
    case_run_name: str = Query(..., description="User-provided case run name"),
    ontology_profile: Optional[str] = Query(
        None,
        description="Optional ontology profile, e.g. full_semantic_pilot",
    ),
) -> CaseRunCollisionCheckResponse:
    """Check whether a named graph for the given rule + case_run_name already exists in Fuseki."""
    try:
        graph_uri = _case_run_graph_uri(
            rule_name,
            case_run_name,
            ontology_profile=ontology_profile,
        )
    except ValueError as exc:
        error_code = (
            "INVALID_ONTOLOGY_PROFILE"
            if "Unsupported ontology_profile" in str(exc)
            else "INVALID_CASE_RUN_NAME"
        )
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": error_code,
                "message": str(exc),
            },
        ) from exc
    try:
        existing_count = FusekiAdapter.get_named_graph_triple_count(graph_uri)
    except Exception:
        existing_count = 0
    return CaseRunCollisionCheckResponse(
        exists=existing_count > 0,
        triple_count=existing_count,
        graph_uri=graph_uri,
    )


@router.post(
    "/ontology-artifact/sync",
    response_model=CaseRunSyncResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def sync_case_run_ontology_artifact(
    request: CaseRunSyncRequest,
    session_id: str = Query(..., description="Session identifier"),
    session: InferenceSession = Depends(_get_session_or_404),
    rule_service: RuleService = Depends(_rule_service),
) -> CaseRunSyncResponse:
    """
    Push a case-run ontology artifact to Fuseki under a user-specified named graph.

    The named graph URI will be:
    ``http://inferra.ai/schema#case-run/rule/{artifact_stem}/{sanitized_case_run_name}``

    When ``ontology_profile`` is ``full_semantic_pilot``, the named graph URI is:
    ``http://inferra.ai/schema#case-run/rule/{artifact_stem}/full-semantic/{sanitized_case_run_name}``

    If a named graph with that URI already exists in Fuseki, the endpoint returns
    ``status: "overwritten"`` so the caller can warn the user before confirming.
    """
    try:
        graph_uri = _case_run_graph_uri(
            session.rule_name,
            request.case_run_name,
            ontology_profile=request.ontology_profile,
        )
    except ValueError as exc:
        error_code = (
            "INVALID_ONTOLOGY_PROFILE"
            if "Unsupported ontology_profile" in str(exc)
            else "INVALID_CASE_RUN_NAME"
        )
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": error_code,
                "message": str(exc),
            },
        ) from exc

    sanitized_name = _sanitize_case_run_name(request.case_run_name)

    ontology_profile_override = request.ontology_profile
    normalized_request_profile: Optional[str] = None
    if request.ontology_profile:
        normalized_request_profile = normalize_ontology_profile(request.ontology_profile)
        if normalized_request_profile == getattr(session, "ontology_profile", None):
            ontology_profile_override = None

    if normalized_request_profile == "full_semantic_pilot":
        _apply_original_decision_context(session, request)

    # Build the artifact from the live session
    artifact = _build_case_run_artifact_for_session(
        session_id=session_id,
        session=session,
        rule_service=rule_service,
        case_name=request.case_run_name,
        ontology_profile_override=ontology_profile_override,
    )
    latest_graph_uri: Optional[str] = None
    version_graph_uri: Optional[str] = None
    if normalized_request_profile == "full_semantic_pilot":
        latest_graph_uri = graph_uri
        if request.versioned:
            version_graph_uri = _case_run_version_graph_uri(
                session.rule_name,
                request.case_run_name,
                artifact.source_hash,
            )
            graph_uri = version_graph_uri

    # Parse the turtle to extract triples for Fuseki insert
    try:
        from rdflib import Graph as RdfGraph

        g = RdfGraph()
        g.parse(data=artifact.turtle, format="turtle")
        triples = [(str(s), str(p), str(o)) for s, p, o in g]
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error_code": "TURTLE_PARSE_FAILED",
                "message": f"Failed to parse case-run TTL: {exc}",
            },
        ) from exc

    # Check for collision (named graph already exists in Fuseki)
    existing_count = FusekiAdapter.get_named_graph_triple_count(graph_uri)
    will_overwrite = existing_count > 0

    # Push to Fuseki
    try:
        FusekiAdapter.execute_sparql_idempotent_insert(
            triples=triples,
            version=artifact.source_hash,
            graph_uri=graph_uri,
        )
        if latest_graph_uri and version_graph_uri:
            FusekiAdapter.execute_sparql_idempotent_insert(
                triples=_latest_full_semantic_pointer_triples(
                    latest_graph_uri=latest_graph_uri,
                    version_graph_uri=version_graph_uri,
                    rule_name=session.rule_name,
                    case_run_name=request.case_run_name,
                    source_hash=artifact.source_hash,
                    semantic_completion_status=artifact.semantic_completion_status,
                    triple_count=len(triples),
                ),
                version=artifact.source_hash,
                graph_uri=latest_graph_uri,
            )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error_code": "FUSEKI_SYNC_FAILED",
                "message": f"Failed to push case-run to Fuseki: {exc}",
            },
        ) from exc

    logger.info(
        "case_run_ontology_synced",
        session_id=session_id,
        rule_name=session.rule_name,
        case_run_name=request.case_run_name,
        sanitized_name=sanitized_name,
        graph_uri=graph_uri,
        latest_graph_uri=latest_graph_uri,
        version_graph_uri=version_graph_uri,
        triple_count=len(triples),
        will_overwrite=will_overwrite,
    )

    return CaseRunSyncResponse(
        status="overwritten" if will_overwrite else "created",
        graph_uri=graph_uri,
        triple_count=len(triples),
        session_id=session_id,
        case_run_name=request.case_run_name,
        latest_graph_uri=latest_graph_uri,
        version_graph_uri=version_graph_uri,
        semantic_completion_status=artifact.semantic_completion_status,
    )


def _case_run_artifact_stem(rule_name: str) -> str:
    """Extract a URL-safe stem from a rule name (mirrors ontology_artifact_service._artifact_stem)."""
    stem = re.sub(r"_sections?_.+$", "", rule_name.strip(), flags=re.IGNORECASE)
    if not stem:
        stem = rule_name.strip()
    stem = re.sub(r"[^a-zA-Z0-9]+", "_", stem).strip("_").lower()
    return stem or "rule_set"


def _sanitize_case_run_name(case_run_name: str) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9_\-]", "_", case_run_name.strip())
    if not sanitized or re.fullmatch(r"_+", sanitized):
        raise ValueError("Case run name must contain at least one alphanumeric character")
    return sanitized


def _case_run_graph_uri(
    rule_name: str,
    case_run_name: str,
    *,
    ontology_profile: Optional[str] = None,
) -> str:
    sanitized_name = _sanitize_case_run_name(case_run_name)
    artifact_stem = _case_run_artifact_stem(rule_name)
    normalized_profile = None
    if ontology_profile:
        try:
            normalized_profile = normalize_ontology_profile(ontology_profile)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
    if normalized_profile == "full_semantic_pilot":
        return (
            "http://inferra.ai/schema#case-run/rule/"
            f"{artifact_stem}/full-semantic/{sanitized_name}/latest"
        )
    return f"http://inferra.ai/schema#case-run/rule/{artifact_stem}/{sanitized_name}"


def _case_run_version_graph_uri(rule_name: str, case_run_name: str, source_hash: str) -> str:
    sanitized_name = _sanitize_case_run_name(case_run_name)
    artifact_stem = _case_run_artifact_stem(rule_name)
    safe_hash = re.sub(r"[^a-zA-Z0-9_\-]", "_", source_hash.strip()) or "unknown"
    return (
        "http://inferra.ai/schema#case-run/rule/"
        f"{artifact_stem}/full-semantic/{sanitized_name}/version/{safe_hash}"
    )


def _latest_full_semantic_pointer_triples(
    *,
    latest_graph_uri: str,
    version_graph_uri: str,
    rule_name: str,
    case_run_name: str,
    source_hash: str,
    semantic_completion_status: Optional[str],
    triple_count: int,
) -> List[Tuple[str, str, str]]:
    updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return [
        (latest_graph_uri, "http://www.w3.org/1999/02/22-rdf-syntax-ns#type", "http://inferra.ai/schema#LatestFullSemanticPointer"),
        (latest_graph_uri, "http://inferra.ai/schema#caseRunName", case_run_name),
        (latest_graph_uri, "http://inferra.ai/schema#ruleName", rule_name),
        (latest_graph_uri, "http://inferra.ai/schema#latestVersionGraph", version_graph_uri),
        (latest_graph_uri, "http://inferra.ai/schema#sourceHash", source_hash),
        (latest_graph_uri, "http://inferra.ai/schema#semanticCompletionStatus", semantic_completion_status or "UNKNOWN"),
        (latest_graph_uri, "http://inferra.ai/schema#versionTripleCount", str(triple_count)),
        (latest_graph_uri, "http://inferra.ai/schema#updatedAt", updated_at),
    ]

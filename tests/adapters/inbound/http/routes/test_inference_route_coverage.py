from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, Request

from src.adapters.inbound.http.routes import inference
from src.adapters.inbound.http.schemas.inference import (
    AnswerEntry,
    DeferQuestionRequest,
    FeedAnswerRequest,
)
from src.adapters.inbound.http.schemas.ontology_artifacts import CaseRunSyncRequest
from src.domain.fact_values import FactValue, FactValueType
from src.domain.nodes.line_type import LineType
from src.domain.session import InferenceContext
from src.domain.state import FactSource
from src.domain.state.feature_flags import FeatureFlags


def _request(user_id: str | None = None, idempotency_key: str | None = None) -> Request:
    headers = []
    if idempotency_key is not None:
        headers.append((b"idempotency-key", idempotency_key.encode()))
    scope = {"type": "http", "headers": headers}
    if user_id is not None:
        scope["inferra_user_id"] = user_id
    return Request(scope)


def _context(**overrides) -> InferenceContext:
    values = {
        "session_id": "session-1",
        "rule_name": "demo_rule",
        "target": "outcome",
        "mandatory": [],
        "fact_store": MagicMock(),
    }
    values.update(overrides)
    return InferenceContext(**values)


def _goal_node(name: str = "outcome") -> MagicMock:
    node = MagicMock()
    node.get_node_name.return_value = name
    return node


def _assessment(active_node=None, goal_name: str = "outcome") -> MagicMock:
    assessment = MagicMock()
    assessment.get_goal_node.return_value = _goal_node(goal_name)
    assessment.get_node_to_be_asked.return_value = active_node
    assessment.get_aux_node_to_be_asked.return_value = None
    return assessment


class _AssessmentState:
    def __init__(self, working_memory=None, *, determined: bool = False, fact_store=None):
        self._working_memory = working_memory or {}
        self._determined = determined
        self._fact_store = fact_store or MagicMock()

    def get_working_memory(self):
        return self._working_memory

    def all_mandatory_node_determined(self):
        return self._determined

    def get_fact_store(self):
        return self._fact_store

    def get_summary_list(self):
        return list(self._working_memory)


class _AnswerEngine:
    def __init__(self, state: _AssessmentState, *, question_lookup_error: bool = False):
        self.state = state
        self.question_lookup_error = question_lookup_error
        self.deferred: list[str] = []

    def get_assessment_state(self):
        return self.state

    def get_questions_from_node_to_be_asked(self, _node):
        if self.question_lookup_error:
            raise RuntimeError("question lookup failed")
        return []

    def feed_answer_to_node(self, *_args):
        return None

    def find_type_of_element_to_be_asked(self, node):
        return {node.get_node_name(): FactValueType.BOOLEAN}

    def defer_question(self, question):
        self.deferred.append(question)


def _session(
    *,
    engine=None,
    assessment=None,
    context: InferenceContext | None = None,
    profile: str = "custom",
):
    return SimpleNamespace(
        session_id="session-1",
        rule_name="demo_rule",
        target_node_name="outcome",
        owner_id=None,
        inference_engine=engine,
        assessment=assessment,
        context=context,
        ontology_profile=profile,
        ontology_profile_source="test",
        feature_flags=FeatureFlags(),
        llm_configuration={},
    )


def test_session_owner_helpers_cover_missing_identity_and_access(monkeypatch):
    monkeypatch.setattr(
        inference,
        "get_feature_flags",
        lambda: FeatureFlags(auth_enabled=True),
    )
    session = SimpleNamespace(owner_id=None)

    with pytest.raises(HTTPException) as exc_info:
        inference._enforce_session_owner(session, _request())
    assert exc_info.value.status_code == 401

    with pytest.raises(HTTPException) as exc_info:
        inference._can_access_session(session, _request())
    assert exc_info.value.status_code == 401
    assert inference._can_access_session(session, _request("user-1")) is True
    session.owner_id = "user-2"
    assert inference._can_access_session(session, _request("user-1")) is False

    monkeypatch.setattr(
        inference,
        "get_feature_flags",
        lambda: FeatureFlags(auth_enabled=False),
    )
    assert inference._can_access_session(session, _request()) is True


def test_refresh_context_adds_new_deferred_questions_and_traces():
    class Engine:
        def get_ontology_auto_answer_trace(self):
            return [{"action": "answered"}]

        def get_ontology_materialization_trace(self):
            return [{"action": "materialized"}]

        def get_ontology_derived_facts(self):
            return ["derived"]

        def get_semantic_question_strategy_trace(self):
            return [
                {"action": "pruned", "question": "skip"},
                {"action": "asked", "question": "keep"},
            ]

        def get_deferred_questions(self):
            return ["", "existing", "new question", "new question"]

    ctx = _context()
    ctx.deferred_semantic_questions = [{"questionName": "existing"}]
    session = _session(engine=Engine(), context=ctx, profile="full_semantic_pilot")
    session.feature_flags = FeatureFlags(ontology_reasoning=True)

    refreshed = inference._refresh_session_context(session, ctx)

    assert refreshed.ontology_profile == "full_semantic_pilot"
    assert refreshed.ontology_reasoning_applied is True
    assert refreshed.ontology_derived_facts == ["derived"]
    assert refreshed.semantic_questions_skipped == [
        {"action": "pruned", "question": "skip"}
    ]
    assert [item.get("question") for item in refreshed.deferred_semantic_questions] == [
        None,
        "new question",
    ]


def test_goal_decision_and_original_decision_context_branches(monkeypatch):
    state = _AssessmentState()
    engine = _AnswerEngine(state)
    assessment = _assessment(goal_name="outcome")
    session = _session(engine=engine, assessment=assessment, context=_context())

    assert inference._session_goal_decision(session) == ("outcome", None)
    assessment.get_goal_node.return_value = None
    assert inference._session_goal_decision(session) == ("outcome", None)
    state._working_memory["outcome"] = None
    assert inference._session_goal_decision(session) == ("outcome", None)
    state._working_memory["outcome"] = "TRUE"
    assert inference._session_goal_decision(session) == ("outcome", "TRUE")
    assert inference._normalized_decision_value(None) == ""
    assert inference._normalized_decision_value(" True ") == "true"

    ctx = _context()
    monkeypatch.setattr(inference, "_session_context", lambda _session: ctx)
    monkeypatch.setattr(
        inference,
        "_session_goal_decision",
        lambda _session: ("outcome", "approved"),
    )
    inference._apply_original_decision_context(
        session,
        CaseRunSyncRequest(case_run_name="case"),
    )
    assert ctx.decision_locked is False

    inference._apply_original_decision_context(
        session,
        CaseRunSyncRequest(
            case_run_name="case",
            original_decision_name="original outcome",
            original_decision_value="denied",
        ),
    )
    assert ctx.decision_locked is True
    assert ctx.semantic_divergence["semantic_decision_value"] == "approved"

    inference._apply_original_decision_context(
        session,
        CaseRunSyncRequest(
            case_run_name="case",
            original_decision_value=" APPROVED ",
        ),
    )
    assert ctx.semantic_divergence is None


def test_list_option_helpers_cover_invalid_and_fixed_declarations():
    invalid = MagicMock()
    invalid.get_value_type.return_value = FactValueType.LIST
    invalid.get_value.return_value = "not-a-list"
    assert inference._options_from_declaration(invalid) == []
    assert inference._options_from_declaration(object()) == []

    declaration = FactValue(
        [FactValue("red", FactValueType.STRING), FactValue("blue", FactValueType.STRING)],
        FactValueType.LIST,
    )
    node_set = MagicMock()
    node_set.get_input_dictionary.return_value = {"unrelated": invalid}
    node_set.get_fact_dictionary.return_value = {"colors": declaration}
    engine = MagicMock()
    engine.get_node_set.return_value = node_set
    options = inference._list_options_for_question(
        engine,
        "choose.colors",
        FactValueType.LIST,
    )
    assert [option.value for option in options] == ["red", "blue"]
    assert inference._question_name_candidates("choose  colors", {"colors": declaration})[0] == "choose  colors"

    no_node_set = MagicMock()
    no_node_set.get_node_set.return_value = None
    assert inference._list_options_for_question(
        no_node_set, "colors", FactValueType.LIST
    ) == []
    node_set.get_fact_dictionary.return_value = {}
    assert inference._list_options_for_question(
        engine, "missing", FactValueType.LIST
    ) == []


@pytest.mark.asyncio
async def test_session_listing_deletion_and_timestamp_helpers(monkeypatch):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first = SimpleNamespace(
        session_id="one",
        rule_name="rule",
        target_node_name="goal",
        owner_id=None,
        created_at=now,
        last_accessed=None,
    )
    second = SimpleNamespace(
        session_id="two",
        rule_name="rule",
        target_node_name="goal",
        owner_id="other",
        created_at=None,
        last_accessed=None,
    )
    service = MagicMock()
    service.list_sessions.return_value = [first, second]
    service.get_session.return_value = first
    service.delete_session.return_value = True
    monkeypatch.setattr(
        inference,
        "_can_access_session",
        lambda session, _request: session.session_id == "one",
    )
    monkeypatch.setattr(inference, "_enforce_session_owner", MagicMock())

    listed = await inference.list_sessions(_request(), service)
    deleted = await inference.delete_session("one", _request(), service)

    assert listed.total_count == 1
    assert listed.sessions[0].created_at == now.isoformat()
    assert listed.sessions[0].last_accessed is None
    assert deleted.deleted is True


@pytest.mark.asyncio
async def test_stalled_question_orchestration_failure_returns_blocked(monkeypatch):
    state = _AssessmentState()

    class Engine:
        def get_next_question_with_goal_name(self, _target):
            return None

        def get_assessment_state(self):
            return state

    class Orchestration:
        async def evaluate_stalled_session(self, _session):
            raise RuntimeError("failed")

    session = _session(engine=Engine(), assessment=_assessment(active_node=None))
    monkeypatch.setattr(
        inference,
        "get_inference_orchestration_service",
        lambda: Orchestration(),
    )

    response = await inference.get_next_question("session-1", session, MagicMock())

    assert response.convergence_state == "PENDING"
    assert response.question_flow_state == "BLOCKED_INCONSISTENT_STATE"


@pytest.mark.asyncio
async def test_iterate_answer_validation_failure_is_mapped(monkeypatch):
    iterate = MagicMock()
    iterate.get_line_type.return_value = LineType.ITERATE
    assessment = _assessment(active_node=iterate)
    assessment.get_aux_node_to_be_asked.return_value = MagicMock()
    session = _session(
        engine=_AnswerEngine(_AssessmentState()),
        assessment=assessment,
    )
    monkeypatch.setattr(
        inference,
        "IterateAnswerPayload",
        MagicMock(side_effect=ValueError("invalid iterate payload")),
    )

    with pytest.raises(HTTPException) as exc_info:
        await inference.feed_answer(
            FeedAnswerRequest(
                question="nested question",
                answer=AnswerEntry(type="string", answer="yes"),
            ),
            _request(),
            "session-1",
            session,
            MagicMock(),
        )

    assert exc_info.value.detail["error_code"] == "INVALID_ITERATE_ANSWER"


@pytest.mark.asyncio
async def test_feed_answer_records_full_semantic_context_after_lookup_failure(monkeypatch):
    active = MagicMock()
    active.get_line_type.return_value = LineType.VALUE_CONCLUSION
    state = _AssessmentState()
    engine = _AnswerEngine(state, question_lookup_error=True)
    ctx = _context()
    session = _session(engine=engine, assessment=_assessment(active), context=ctx)
    monkeypatch.setattr(inference, "_session_context", lambda _session: ctx)

    response = await inference.feed_answer(
        FeedAnswerRequest(
            question="semantic question",
            answer=AnswerEntry(type="string", answer="yes"),
            answer_context="FULL_SEMANTIC_COMPLETION",
        ),
        _request(),
        "session-1",
        session,
        MagicMock(),
    )

    assert response.has_more_questions is True
    assert ctx.post_decision_answer_names == ["semantic question"]
    assert ctx.semantic_completion_status == "IN_PROGRESS"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("profile", "deferred", "expected_status"),
    [
        ("custom", [{"question": "later"}], "PARTIAL"),
        ("full_semantic_pilot", [], "COMPLETE"),
    ],
)
async def test_completed_answer_sets_semantic_completion_state(
    monkeypatch, profile, deferred, expected_status
):
    active = MagicMock()
    active.get_line_type.return_value = LineType.VALUE_CONCLUSION
    state = _AssessmentState(
        {"outcome": FactValue(True, FactValueType.BOOLEAN)},
        determined=True,
    )
    engine = _AnswerEngine(state)
    ctx = _context(ontology_profile=profile)
    ctx.deferred_semantic_questions = deferred
    session = _session(
        engine=engine,
        assessment=_assessment(active),
        context=ctx,
        profile=profile,
    )
    monkeypatch.setattr(inference, "_session_context", lambda _session: ctx)
    monkeypatch.setattr(inference, "_run_ontology_post_reasoning", MagicMock())

    response = await inference.feed_answer(
        FeedAnswerRequest(
            question="input",
            answer=AnswerEntry(type="boolean", answer=True),
        ),
        _request(),
        "session-1",
        session,
        MagicMock(),
    )

    assert response.has_more_questions is False
    assert ctx.semantic_completion_status == expected_status
    if profile == "full_semantic_pilot":
        assert ctx.semantic_completion_policy == "INTERACTIVE_WITH_DEFERRED_ALLOWED"


@pytest.mark.asyncio
async def test_defer_question_validation_and_success_paths(monkeypatch):
    no_active_session = _session(
        engine=_AnswerEngine(_AssessmentState()),
        assessment=_assessment(active_node=None),
    )
    with pytest.raises(HTTPException, match="blank"):
        await inference.defer_question(
            DeferQuestionRequest(question="  "),
            "session-1",
            no_active_session,
            MagicMock(),
        )
    with pytest.raises(HTTPException, match="No active"):
        await inference.defer_question(
            DeferQuestionRequest(question="question"),
            "session-1",
            no_active_session,
            MagicMock(),
        )

    active = MagicMock()
    active.get_node_name.return_value = "active node"
    active.get_variable_name.return_value = "active variable"
    engine = _AnswerEngine(_AssessmentState(), question_lookup_error=True)
    session = _session(engine=engine, assessment=_assessment(active))
    with pytest.raises(HTTPException) as exc_info:
        await inference.defer_question(
            DeferQuestionRequest(question="not active"),
            "session-1",
            session,
            MagicMock(),
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["active_questions"] == [
        "active node",
        "active variable",
    ]

    engine.question_lookup_error = False
    engine.get_questions_from_node_to_be_asked = lambda _node: ["active question"]
    ctx = _context()
    monkeypatch.setattr(inference, "_session_context", lambda _session: ctx)
    response = await inference.defer_question(
        DeferQuestionRequest(
            question="active question",
            node_name="semantic node",
            reason="operator deferred",
            defer_all_remaining=True,
        ),
        "session-1",
        session,
        MagicMock(),
    )
    assert response.deferred_count == 1
    assert ctx.semantic_completion_policy == "DEFER_ALL_REMAINING"
    assert ctx.deferred_semantic_questions[0]["node_name"] == "semantic node"

    response = await inference.defer_question(
        DeferQuestionRequest(question="active question"),
        "session-1",
        session,
        MagicMock(),
    )
    assert response.deferred_count == 1
    assert ctx.semantic_completion_policy == "INTERACTIVE_WITH_DEFERRED_ALLOWED"


@pytest.mark.asyncio
async def test_summary_reports_semantic_fact_source(monkeypatch):
    value = FactValue("derived", FactValueType.STRING)
    fact_store = MagicMock()
    fact_store.get_fact_sources.return_value = {FactSource.SEMANTIC}
    state = _AssessmentState({"semantic fact": value}, determined=False, fact_store=fact_store)
    engine = _AnswerEngine(state)
    session = _session(engine=engine, assessment=_assessment())
    session.feature_flags = FeatureFlags(enriched_api=True)
    ctx = _context()
    monkeypatch.setattr(inference, "_session_context", lambda _session: ctx)
    monkeypatch.setattr(inference, "_convergence_state", lambda _session: "PENDING")

    response = await inference.get_summary("session-1", 0, 0, session)

    assert response.summary[0].fact_source == FactSource.SEMANTIC.value


@pytest.mark.asyncio
async def test_summary_tolerates_fact_source_failure(monkeypatch):
    value = FactValue("asserted", FactValueType.STRING)
    fact_store = MagicMock()
    fact_store.get_fact_sources.side_effect = RuntimeError("source unavailable")
    state = _AssessmentState({"fact": value}, fact_store=fact_store)
    session = _session(engine=_AnswerEngine(state), assessment=_assessment())
    session.feature_flags = FeatureFlags(enriched_api=True)
    monkeypatch.setattr(inference, "_session_context", lambda _session: _context())
    monkeypatch.setattr(inference, "_convergence_state", lambda _session: "PENDING")

    response = await inference.get_summary("session-1", 0, 0, session)

    assert response.summary[0].node_text == "fact"
    assert response.summary[0].fact_source is None


def test_artifact_override_maps_invalid_profile(monkeypatch):
    session = _session(
        engine=_AnswerEngine(_AssessmentState()),
        assessment=_assessment(),
        context=_context(),
    )
    rule_service = MagicMock()
    rule_service.get_rule_ontology_data.return_value = {}
    monkeypatch.setattr(inference, "_session_context", lambda _session: _context())
    monkeypatch.setattr(
        inference,
        "normalize_ontology_profile",
        MagicMock(side_effect=ValueError("unsupported profile")),
    )

    with pytest.raises(HTTPException) as exc_info:
        inference._build_case_run_artifact_for_session(
            session_id="session-1",
            session=session,
            rule_service=rule_service,
            ontology_profile_override="invalid",
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_collision_check_maps_names_profiles_and_fuseki_failures(monkeypatch):
    with pytest.raises(HTTPException) as exc_info:
        await inference.check_case_run_collision("rule", "___", None)
    assert exc_info.value.detail["error_code"] == "INVALID_CASE_RUN_NAME"

    with pytest.raises(HTTPException) as exc_info:
        await inference.check_case_run_collision("rule", "case", "invalid-profile")
    assert exc_info.value.detail["error_code"] == "INVALID_ONTOLOGY_PROFILE"

    monkeypatch.setattr(
        inference.FusekiAdapter,
        "get_named_graph_triple_count",
        MagicMock(side_effect=RuntimeError("offline")),
    )
    response = await inference.check_case_run_collision("rule", "case", None)
    assert response.exists is False
    assert response.triple_count == 0

    monkeypatch.setattr(
        inference.FusekiAdapter,
        "get_named_graph_triple_count",
        MagicMock(return_value=2),
    )
    response = await inference.check_case_run_collision("rule", "case", None)
    assert response.exists is True
    assert response.triple_count == 2


def _artifact(turtle: str = "<urn:s> <urn:p> <urn:o> ."):
    return SimpleNamespace(
        turtle=turtle,
        source_hash="source/hash:v1",
        semantic_completion_status="COMPLETE",
    )


@pytest.mark.asyncio
async def test_sync_full_semantic_versioned_artifact_success(monkeypatch):
    session = _session(
        engine=_AnswerEngine(_AssessmentState()),
        assessment=_assessment(),
        profile="full_semantic_pilot",
    )
    build = MagicMock(return_value=_artifact())
    apply_original = MagicMock()
    insert = MagicMock()
    monkeypatch.setattr(inference, "_build_case_run_artifact_for_session", build)
    monkeypatch.setattr(inference, "_apply_original_decision_context", apply_original)
    monkeypatch.setattr(
        inference.FusekiAdapter,
        "get_named_graph_triple_count",
        MagicMock(return_value=3),
    )
    monkeypatch.setattr(
        inference.FusekiAdapter,
        "execute_sparql_idempotent_insert",
        insert,
    )
    request = CaseRunSyncRequest(
        case_run_name="Case One",
        ontology_profile="full_semantic_pilot",
        versioned=True,
        original_decision_name="outcome",
        original_decision_value="true",
    )

    response = await inference.sync_case_run_ontology_artifact(
        request,
        "session-1",
        session,
        MagicMock(),
    )

    assert response.status == "overwritten"
    assert response.latest_graph_uri.endswith("/latest")
    assert "/version/source_hash_v1" in response.version_graph_uri
    assert insert.call_count == 2
    assert build.call_args.kwargs["ontology_profile_override"] is None
    apply_original.assert_called_once_with(session, request)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("profile", "case_name", "error_code"),
    [
        (None, "___", "INVALID_CASE_RUN_NAME"),
        ("invalid-profile", "case", "INVALID_ONTOLOGY_PROFILE"),
    ],
)
async def test_sync_rejects_invalid_graph_inputs(profile, case_name, error_code):
    session = _session(
        engine=_AnswerEngine(_AssessmentState()),
        assessment=_assessment(),
    )
    with pytest.raises(HTTPException) as exc_info:
        await inference.sync_case_run_ontology_artifact(
            CaseRunSyncRequest(case_run_name=case_name, ontology_profile=profile),
            "session-1",
            session,
            MagicMock(),
        )
    assert exc_info.value.detail["error_code"] == error_code


@pytest.mark.asyncio
async def test_sync_maps_turtle_parse_and_fuseki_insert_failures(monkeypatch):
    session = _session(
        engine=_AnswerEngine(_AssessmentState()),
        assessment=_assessment(),
    )
    monkeypatch.setattr(
        inference,
        "_build_case_run_artifact_for_session",
        MagicMock(return_value=_artifact("not valid turtle")),
    )
    with pytest.raises(HTTPException) as exc_info:
        await inference.sync_case_run_ontology_artifact(
            CaseRunSyncRequest(case_run_name="case"),
            "session-1",
            session,
            MagicMock(),
        )
    assert exc_info.value.detail["error_code"] == "TURTLE_PARSE_FAILED"

    monkeypatch.setattr(
        inference,
        "_build_case_run_artifact_for_session",
        MagicMock(return_value=_artifact()),
    )
    monkeypatch.setattr(
        inference.FusekiAdapter,
        "get_named_graph_triple_count",
        MagicMock(return_value=0),
    )
    monkeypatch.setattr(
        inference.FusekiAdapter,
        "execute_sparql_idempotent_insert",
        MagicMock(side_effect=RuntimeError("offline")),
    )
    with pytest.raises(HTTPException) as exc_info:
        await inference.sync_case_run_ontology_artifact(
            CaseRunSyncRequest(case_run_name="case"),
            "session-1",
            session,
            MagicMock(),
        )
    assert exc_info.value.detail["error_code"] == "FUSEKI_SYNC_FAILED"


def test_case_run_uri_and_pointer_helpers_cover_fallbacks(monkeypatch):
    assert inference._case_run_artifact_stem("_section_x") == "section_x"
    assert inference._case_run_artifact_stem("***") == "rule_set"
    with pytest.raises(ValueError, match="alphanumeric"):
        inference._sanitize_case_run_name("___")
    with pytest.raises(ValueError, match="Unsupported"):
        inference._case_run_graph_uri(
            "rule",
            "case",
            ontology_profile="invalid-profile",
        )
    assert inference._case_run_version_graph_uri("rule", "case", "") .endswith(
        "/version/unknown"
    )

    monkeypatch.setattr(inference.time, "strftime", lambda *_args: "2026-01-01T00:00:00Z")
    triples = inference._latest_full_semantic_pointer_triples(
        latest_graph_uri="urn:latest",
        version_graph_uri="urn:version",
        rule_name="rule",
        case_run_name="case",
        source_hash="hash",
        semantic_completion_status=None,
        triple_count=4,
    )
    assert len(triples) == 8
    assert ("urn:latest", f"{inference.INF_NS if hasattr(inference, 'INF_NS') else 'http://inferra.ai/schema#'}semanticCompletionStatus", "UNKNOWN") in triples

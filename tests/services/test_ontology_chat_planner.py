import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.services import ontology_chat_planner as planner
from src.services.ontology_chat_planner import _planner_context_payload, _planner_prompt


def test_planner_prompt_guides_answer_fact_queries_away_from_case_run():
    payload = _planner_context_payload(
        question=(
            "Show the user-provided answers and fact values in this case run, "
            "including question name, value, fact source, and related node name."
        ),
        selected_graphs=["http://inferra.ai/schema#case-run/rule/example/full-semantic/case-a"],
        graph_counts={
            "http://inferra.ai/schema#case-run/rule/example/full-semantic/case-a": 123
        },
        row_limit=100,
        timeout_seconds=10,
        predicate_summary=[],
        sample_triples=[],
        case_run_metadata=[],
    )

    recipes = payload["query_recipes"]
    answer_recipe = next(
        recipe
        for recipe in recipes
        if recipe["intent"] == "user_provided_answers_and_fact_values"
    )
    prompt = _planner_prompt(payload)

    assert "inf:CaseFact" in answer_recipe["sparql_shape"]
    assert "inf:SemanticQuestionStrategyTrace" in answer_recipe["sparql_shape"]
    assert '"asserted"' in answer_recipe["sparql_shape"]
    assert "Never use rdf:type inf:CaseRun" in prompt
    assert "questionName, value, factSource, or nodeName" in prompt


def _configured_llm(*, content: str = "", error: Exception | None = None):
    create = MagicMock()
    if error is not None:
        create.side_effect = error
    else:
        create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )
    return SimpleNamespace(
        client=SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        ),
        model="planner-model",
        provider_id="provider-one",
        timeout=9,
    )


def _plan(monkeypatch, llm):
    monkeypatch.setattr(planner, "_axiom_llm_client", lambda: llm)
    monkeypatch.setattr(
        planner,
        "_selected_graph_predicate_summary",
        lambda *_args, **_kwargs: [{"predicate": "inf:name"}],
    )
    monkeypatch.setattr(
        planner,
        "_selected_graph_sample_triples",
        lambda *_args, **_kwargs: [{"subject": "inf:case"}],
    )
    monkeypatch.setattr(
        planner,
        "_selected_graph_case_run_metadata",
        lambda *_args, **_kwargs: [{"case_name": "Case A"}],
    )
    return planner.plan_ontology_chat_query(
        question="What happened?",
        selected_graphs=["https://example.test/graph/one"],
        graph_counts={"https://example.test/graph/one": 3},
        row_limit=25,
        timeout_seconds=4,
    )


@pytest.mark.parametrize(
    "llm",
    [
        None,
        SimpleNamespace(client=None, model="planner-model"),
        SimpleNamespace(client=object(), model=""),
    ],
)
def test_plan_abstains_when_axiom_llm_is_not_configured(monkeypatch, llm):
    result = _plan(monkeypatch, llm)

    assert result.status == "abstain"
    assert result.provenance == {"planner": "llm", "llm_configured": False}
    assert "configured" in result.rationale


def test_plan_returns_bounded_query_candidate(monkeypatch):
    llm = _configured_llm(
        content=json.dumps(
            {
                "status": "query",
                "sparql": "SELECT * WHERE { GRAPH <https://example.test/graph/one> { ?s ?p ?o } } LIMIT 25",
                "rationale": "Uses the selected graph.",
                "confidence": 1.7,
                "provenance": {"used_predicates": ["inf:name"]},
            }
        )
    )

    result = _plan(monkeypatch, llm)

    assert result.status == "query"
    assert result.confidence == 1.0
    assert result.provenance == {
        "planner": "llm",
        "provider_id": "provider-one",
        "model_id": "planner-model",
        "predicate_summary_count": 1,
        "sample_triple_count": 1,
        "case_run_metadata_count": 1,
        "used_predicates": ["inf:name"],
    }
    assert result.as_candidate_payload()["sparql"].startswith("SELECT")
    create = llm.client.chat.completions.create
    assert create.call_args.kwargs["temperature"] == 0
    assert create.call_args.kwargs["timeout"] == 9


def test_plan_uses_default_query_rationale_and_ignores_non_dict_provenance(monkeypatch):
    llm = _configured_llm(
        content=json.dumps(
            {
                "status": "query",
                "sparql": "SELECT * WHERE { GRAPH <https://example.test/graph/one> { ?s ?p ?o } } LIMIT 1",
                "confidence": "0.4",
                "provenance": ["not", "a", "mapping"],
            }
        )
    )

    result = _plan(monkeypatch, llm)

    assert result.rationale == "LLM generated a graph-scoped SPARQL query."
    assert result.confidence == 0.4
    assert "used_predicates" not in result.provenance


def test_plan_abstains_when_provider_call_fails(monkeypatch):
    result = _plan(monkeypatch, _configured_llm(error=RuntimeError("provider down")))

    assert result.status == "abstain"
    assert result.provenance["error"] == "provider down"


def test_plan_abstains_when_response_is_too_large(monkeypatch):
    result = _plan(monkeypatch, _configured_llm(content="x" * (planner.MAX_LLM_RESPONSE_CHARS + 1)))

    assert result.status == "abstain"
    assert result.provenance["response_length"] == planner.MAX_LLM_RESPONSE_CHARS + 1


@pytest.mark.parametrize(
    ("content", "expected_rationale"),
    [
        ("not json", "LLM did not return valid ontology query JSON."),
        (json.dumps({"status": "unsupported"}), "LLM returned an unsupported ontology query status."),
        (json.dumps({"status": "query"}), "LLM returned query status without SPARQL."),
    ],
)
def test_plan_abstains_for_invalid_contracts(monkeypatch, content, expected_rationale):
    result = _plan(monkeypatch, _configured_llm(content=content))

    assert result.status == "abstain"
    assert result.rationale == expected_rationale


def test_plan_preserves_llm_abstention(monkeypatch):
    result = _plan(
        monkeypatch,
        _configured_llm(
            content=json.dumps(
                {
                    "status": "abstain",
                    "rationale": "Graph lacks the predicate.",
                    "confidence": -2,
                    "provenance": {"reason": "missing_predicate"},
                }
            )
        ),
    )

    assert result.status == "abstain"
    assert result.confidence == 0.0
    assert result.provenance == {"planner": "llm", "reason": "missing_predicate"}


def test_candidate_payload_omits_empty_sparql():
    payload = planner.OntologyChatPlan(rationale="No query").as_candidate_payload()

    assert "sparql" not in payload


def test_axiom_client_uses_product_configuration_and_closes_session(monkeypatch):
    db = MagicMock()
    resolved = object()
    service = MagicMock()
    service.resolve_product_client_config.return_value = resolved
    configured = object()

    monkeypatch.setattr(planner, "SessionLocal", lambda: db)
    monkeypatch.setattr(planner, "LLMProductConfigurationRepository", lambda value: ("repo", value))
    monkeypatch.setattr(planner, "LLMConfigurationService", lambda repository: service)
    client_factory = MagicMock(return_value=configured)
    monkeypatch.setattr(planner, "LLMClient", client_factory)

    assert planner._axiom_llm_client() is configured
    service.resolve_product_client_config.assert_called_once_with("axiom")
    client_factory.assert_called_once_with(resolved_config=resolved)
    db.close.assert_called_once_with()


@pytest.mark.parametrize("resolution_fails", [False, True])
def test_axiom_client_falls_back_when_product_configuration_is_unavailable(
    monkeypatch, resolution_fails
):
    db = MagicMock()
    service = MagicMock()
    if resolution_fails:
        service.resolve_product_client_config.side_effect = RuntimeError("database unavailable")
    else:
        service.resolve_product_client_config.return_value = None
    fallback = SimpleNamespace(client=object(), model="fallback-model")

    monkeypatch.setattr(planner, "SessionLocal", lambda: db)
    monkeypatch.setattr(planner, "LLMProductConfigurationRepository", lambda value: value)
    monkeypatch.setattr(planner, "LLMConfigurationService", lambda repository: service)
    monkeypatch.setattr(planner, "LLMClient", lambda *args, **kwargs: fallback)

    assert planner._axiom_llm_client() is fallback
    db.close.assert_called_once_with()


def test_axiom_client_handles_session_failure_and_unconfigured_fallback(monkeypatch):
    fallback = SimpleNamespace(client=None, model=None)

    def fail_session():
        raise RuntimeError("no database")

    monkeypatch.setattr(planner, "SessionLocal", fail_session)
    monkeypatch.setattr(planner, "LLMClient", lambda: fallback)

    assert planner._axiom_llm_client() is None


def test_predicate_summary_compacts_known_namespaces(monkeypatch):
    execute = MagicMock(
        return_value=[
            {
                "graph": {"value": "https://example.test/graph/one"},
                "predicate": {"value": planner.ALLOWED_NAMESPACES["inf"] + "name"},
                "count": {"value": "4"},
            }
        ]
    )
    monkeypatch.setattr(planner.FusekiAdapter, "execute_guarded_select", execute)

    result = planner._selected_graph_predicate_summary(
        ["https://example.test/graph/one"], timeout_seconds=3
    )

    assert result == [
        {
            "graph": "https://example.test/graph/one",
            "predicate": "inf:name",
            "predicate_uri": planner.ALLOWED_NAMESPACES["inf"] + "name",
            "count": "4",
        }
    ]
    assert "LIMIT 40" in execute.call_args.args[0]


def test_sample_triples_compact_values_and_clamp_limit(monkeypatch):
    execute = MagicMock(
        return_value=[
            {
                "graph": {"value": "https://example.test/graph/one"},
                "subject": {"value": planner.ALLOWED_NAMESPACES["inf"] + "case"},
                "predicate": {"value": planner.ALLOWED_NAMESPACES["rdf"] + "type"},
                "object": {"value": planner.ALLOWED_NAMESPACES["inf"] + "CaseRun"},
            }
        ]
    )
    monkeypatch.setattr(planner.FusekiAdapter, "execute_guarded_select", execute)

    result = planner._selected_graph_sample_triples(
        ["https://example.test/graph/one"], limit=100, timeout_seconds=3
    )

    assert result[0]["subject"] == "inf:case"
    assert result[0]["predicate"] == "rdf:type"
    assert result[0]["object"] == "inf:CaseRun"
    assert f"LIMIT {planner.MAX_SAMPLE_TRIPLES}" in execute.call_args.args[0]


def test_case_run_metadata_maps_optional_bindings(monkeypatch):
    execute = MagicMock(
        return_value=[
            {
                "graph": {"value": "https://example.test/graph/one"},
                "caseRun": {"value": planner.ALLOWED_NAMESPACES["inf"] + "case-a"},
                "caseName": {"value": "Case A"},
                "ruleName": {"value": "Rule A"},
                "targetNodeName": {"value": "eligible"},
                "ontologyProfile": {"value": "default"},
                "deterministicOutcomeName": {"value": "eligible"},
                "deterministicOutcomeValue": {"value": "true"},
            }
        ]
    )
    monkeypatch.setattr(planner.FusekiAdapter, "execute_guarded_select", execute)

    result = planner._selected_graph_case_run_metadata(
        ["https://example.test/graph/one"], timeout_seconds=3
    )

    assert result == [
        {
            "graph": "https://example.test/graph/one",
            "case_run": "inf:case-a",
            "case_run_uri": planner.ALLOWED_NAMESPACES["inf"] + "case-a",
            "case_name": "Case A",
            "rule_name": "Rule A",
            "target_node_name": "eligible",
            "ontology_profile": "default",
            "deterministic_outcome_name": "eligible",
            "deterministic_outcome_value": "true",
        }
    ]


@pytest.mark.parametrize(
    "collector,args",
    [
        (planner._selected_graph_predicate_summary, {"timeout_seconds": 2}),
        (planner._selected_graph_sample_triples, {"limit": 2, "timeout_seconds": 2}),
        (planner._selected_graph_case_run_metadata, {"timeout_seconds": 2}),
    ],
)
def test_graph_context_collectors_fail_closed(monkeypatch, collector, args):
    monkeypatch.setattr(
        planner.FusekiAdapter,
        "execute_guarded_select",
        MagicMock(side_effect=RuntimeError("Fuseki unavailable")),
    )

    assert collector(["https://example.test/graph/one"], **args) == []


@pytest.mark.parametrize(
    ("graph_uri", "expected"),
    [
        ("https://example.test/full-semantic/case", "full_semantic_case_run"),
        ("https://example.test/case-run/rule/x", "full_semantic_case_run"),
        ("https://example.test/projection/rule/x", "rule_projection"),
        ("https://example.test/artifact/full/x", "case_run_full_artifact"),
        ("https://example.test/other", "named_graph"),
    ],
)
def test_graph_kind_classification(graph_uri, expected):
    assert planner._graph_kind(graph_uri) == expected


def test_planner_context_includes_counts_and_graph_kinds():
    payload = planner._planner_context_payload(
        question="q",
        selected_graphs=["https://example.test/projection/rule/x", "https://example.test/other"],
        graph_counts={"https://example.test/projection/rule/x": "7"},
        row_limit=5,
        timeout_seconds=2,
        predicate_summary=[],
        sample_triples=[],
        case_run_metadata=[],
    )

    assert payload["graph_metadata"] == [
        {
            "uri": "https://example.test/projection/rule/x",
            "triple_count": 7,
            "known_graph_kind": "rule_projection",
        },
        {
            "uri": "https://example.test/other",
            "triple_count": 0,
            "known_graph_kind": "named_graph",
        },
    ]
    assert payload["guardrails"]["operation"] == "SELECT only"


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ('```json\n{"status": "abstain"}\n```', {"status": "abstain"}),
        ('prefix text {"status": "query"} suffix text', {"status": "query"}),
    ],
)
def test_parse_json_object_accepts_fenced_or_embedded_json(content, expected):
    assert planner._parse_json_object(content) == expected


@pytest.mark.parametrize("content", ["[]", "no object here"])
def test_parse_json_object_rejects_non_object_responses(content):
    with pytest.raises(ValueError):
        planner._parse_json_object(content)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, None), ("bad", None), (object(), None), (-1, 0.0), (2, 1.0), ("0.25", 0.25)],
)
def test_optional_float_is_bounded(value, expected):
    assert planner._optional_float(value) == expected


def test_binding_compaction_and_mapping_helpers():
    assert planner._binding_value({"x": {"value": 7}}, "x") == "7"
    assert planner._binding_value({"x": "raw"}, "x") == "raw"
    assert planner._binding_value({}, "x") == ""
    assert planner._compact_uri("https://outside.test/value") == "https://outside.test/value"
    assert planner._dict_or_empty({"a": 1}) == {"a": 1}
    assert planner._dict_or_empty([("a", 1)]) == {}

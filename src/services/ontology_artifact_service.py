import json
import re
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import quote

from src.adapters.outbound.ontology.fuseki_adapter import INF_NS, FusekiAdapter
from src.adapters.outbound.ontology.inferra_to_rdf_compiler import COMPILER_VERSION

RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
PROV_NS = "http://www.w3.org/ns/prov#"
ARTIFACT_MEDIA_TYPE = "text/turtle"
ADVISORY_GUARDRAIL = "ontology_advisory_no_rule_execution_override"


@dataclass(frozen=True)
class OntologyArtifact:
    artifact_name: str
    artifact_kind: str
    media_type: str
    rule_name: str
    graph_uri: str
    source_hash: str
    compiler_version: str
    triple_count: int
    turtle: str
    projection_graph_uri: str | None = None
    artifact_uri: str | None = None
    download_url: str | None = None
    session_id: str | None = None
    case_name: str | None = None
    target_node_name: str | None = None
    deterministic_outcome_ref: str | None = None
    semantic_completion_status: str | None = None
    latest_graph_uri: str | None = None
    version_graph_uri: str | None = None

    def metadata_dict(self) -> dict[str, Any]:
        return {
            "artifact_name": self.artifact_name,
            "artifact_kind": self.artifact_kind,
            "media_type": self.media_type,
            "rule_name": self.rule_name,
            "graph_uri": self.graph_uri,
            "projection_graph_uri": self.projection_graph_uri,
            "source_hash": self.source_hash,
            "compiler_version": self.compiler_version,
            "triple_count": self.triple_count,
            "artifact_uri": self.artifact_uri,
            "download_url": self.download_url,
            "session_id": self.session_id,
            "case_name": self.case_name,
            "target_node_name": self.target_node_name,
            "deterministic_outcome_ref": self.deterministic_outcome_ref,
            "semantic_completion_status": self.semantic_completion_status,
            "latest_graph_uri": self.latest_graph_uri,
            "version_graph_uri": self.version_graph_uri,
        }

    def response_dict(self) -> dict[str, Any]:
        return {
            **self.metadata_dict(),
            "turtle": self.turtle,
        }


def rule_artifact_name(rule_name: str) -> str:
    return f"{_artifact_stem(rule_name)}_ontology.ttl"


def full_artifact_name(rule_name: str) -> str:
    return f"{_artifact_stem(rule_name)}_full_ontology.ttl"


def build_rule_set_ontology_artifact(
    *,
    rule_name: str,
    triples: Sequence[tuple[str, str, str]],
    source_hash: str,
    graph_uri: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> OntologyArtifact:
    name = rule_artifact_name(rule_name)
    projection_graph_uri = graph_uri or FusekiAdapter.rule_projection_graph_uri(rule_name)
    artifact_uri = f"{INF_NS}artifact/rule-set/{_safe_uri_component(name)}"
    extra_triples = [
        (artifact_uri, RDF_TYPE, f"{INF_NS}OntologyArtifact"),
        (artifact_uri, RDF_TYPE, f"{INF_NS}RuleSetOntologyArtifact"),
        (artifact_uri, f"{INF_NS}name", name),
        (artifact_uri, f"{INF_NS}ruleName", rule_name),
        (artifact_uri, f"{INF_NS}mediaType", ARTIFACT_MEDIA_TYPE),
        (artifact_uri, f"{INF_NS}sourceHash", source_hash),
        (artifact_uri, f"{INF_NS}compilerVersion", COMPILER_VERSION),
        (artifact_uri, f"{INF_NS}graphUri", projection_graph_uri),
        (artifact_uri, f"{INF_NS}advisoryGuardrail", ADVISORY_GUARDRAIL),
    ]
    if metadata:
        for key in (
            "sync_status",
            "sync_timestamp",
            "integrity_status",
            "integrity_mismatch_reason",
            "job_id",
        ):
            value = metadata.get(key)
            if value is not None:
                extra_triples.append((artifact_uri, f"{INF_NS}{_camel_case(key)}", str(value)))

    turtle, triple_count = _serialize_turtle([*triples, *extra_triples])
    return OntologyArtifact(
        artifact_name=name,
        artifact_kind="rule_set",
        media_type=ARTIFACT_MEDIA_TYPE,
        rule_name=rule_name,
        graph_uri=projection_graph_uri,
        projection_graph_uri=projection_graph_uri,
        source_hash=source_hash,
        compiler_version=COMPILER_VERSION,
        triple_count=triple_count,
        turtle=turtle,
        artifact_uri=artifact_uri,
        download_url=f"/api/v1/rules/{quote(rule_name, safe='')}/ontology/artifact/download",
    )


def build_case_run_ontology_artifact(
    *,
    rule_ontology: Mapping[str, Any],
    session_id: str,
    target_node_name: str,
    facts: Sequence[Mapping[str, Any]],
    case_name: str | None = None,
    reasoning_mode: str = "DEDUCTION",
    confidence: float = 1.0,
    status: str | None = None,
    ontology_profile: str | None = None,
    ontology_profile_source: str | None = None,
    ontology_flags: Mapping[str, Any] | None = None,
    ontology_auto_answer_trace: Sequence[Mapping[str, Any]] | None = None,
    ontology_materialization_trace: Sequence[Mapping[str, Any]] | None = None,
    semantic_question_strategy_trace: Sequence[Mapping[str, Any]] | None = None,
    ontology_derived_facts: Sequence[str] | None = None,
    deferred_questions: Sequence[Mapping[str, Any]] | None = None,
    post_decision_answer_names: Sequence[str] | None = None,
    semantic_completion_status: str | None = None,
    semantic_completion_policy: str | None = None,
    decision_locked: bool = False,
    original_decision_name: str | None = None,
    original_decision_value: str | None = None,
    semantic_divergence: Mapping[str, Any] | None = None,
) -> OntologyArtifact:
    rule_name = str(rule_ontology.get("rule_name") or "")
    rule_source_hash = str(rule_ontology.get("source_hash") or "")
    projection_graph_uri = str(
        rule_ontology.get("graph_uri") or FusekiAdapter.rule_projection_graph_uri(rule_name)
    )
    normalized_facts = _normalise_fact_payload(facts)
    full_source_hash = _case_source_hash(
        rule_name=rule_name,
        rule_source_hash=rule_source_hash,
        session_id=session_id,
        target_node_name=target_node_name,
        facts=normalized_facts,
        ontology_profile=ontology_profile or "custom",
        ontology_profile_source=ontology_profile_source or "environment",
        ontology_flags=dict(ontology_flags or {}),
        ontology_auto_answer_trace=ontology_auto_answer_trace or (),
        ontology_materialization_trace=ontology_materialization_trace or (),
        semantic_question_strategy_trace=semantic_question_strategy_trace or (),
        ontology_derived_facts=ontology_derived_facts or (),
        deferred_questions=deferred_questions or (),
        post_decision_answer_names=post_decision_answer_names or (),
        semantic_completion_status=semantic_completion_status or "UNKNOWN",
        semantic_completion_policy=semantic_completion_policy or "UNSPECIFIED",
        decision_locked=decision_locked,
        original_decision_name=original_decision_name,
        original_decision_value=original_decision_value,
        semantic_divergence=semantic_divergence or {},
    )
    name = full_artifact_name(rule_name)
    graph_uri = f"{INF_NS}artifact/full/{_artifact_stem(rule_name)}/{full_source_hash}"
    artifact_uri = f"{INF_NS}artifact/case-run/{_safe_uri_component(name)}"
    session_uri = f"{INF_NS}session/{_safe_uri_component(session_id)}"
    rule_uri = f"{INF_NS}rule/{_safe_uri_component(rule_name)}"
    deterministic_ref = None
    derived_fact_names = {str(name) for name in (ontology_derived_facts or ())}
    post_decision_names = {str(name) for name in (post_decision_answer_names or ())}
    deferred_question_payloads = [dict(item) for item in (deferred_questions or ())]
    completion_status = (
        semantic_completion_status
        or ("PARTIAL" if deferred_question_payloads else "COMPLETE")
    )

    extra_triples: list[tuple[str, str, str]] = [
        (artifact_uri, RDF_TYPE, f"{INF_NS}OntologyArtifact"),
        (artifact_uri, RDF_TYPE, f"{INF_NS}CaseRunFullOntologyArtifact"),
        (artifact_uri, f"{INF_NS}name", name),
        (artifact_uri, f"{INF_NS}ruleName", rule_name),
        (artifact_uri, f"{INF_NS}mediaType", ARTIFACT_MEDIA_TYPE),
        (artifact_uri, f"{INF_NS}sourceHash", full_source_hash),
        (artifact_uri, f"{INF_NS}compilerVersion", COMPILER_VERSION),
        (artifact_uri, f"{INF_NS}graphUri", graph_uri),
        (artifact_uri, f"{INF_NS}projectionGraphUri", projection_graph_uri),
        (artifact_uri, f"{INF_NS}advisoryGuardrail", ADVISORY_GUARDRAIL),
        (artifact_uri, f"{PROV_NS}wasDerivedFrom", projection_graph_uri),
        (session_uri, RDF_TYPE, f"{INF_NS}CaseRun"),
        (session_uri, f"{INF_NS}sessionId", session_id),
        (session_uri, f"{INF_NS}caseName", case_name or session_id),
        (session_uri, f"{INF_NS}ruleName", rule_name),
        (session_uri, f"{INF_NS}targetNodeName", target_node_name),
        (session_uri, f"{INF_NS}reasoningMode", reasoning_mode),
        (session_uri, f"{INF_NS}confidence", str(confidence)),
        (session_uri, f"{INF_NS}status", status or "UNKNOWN"),
        (session_uri, f"{INF_NS}ontologyProfile", ontology_profile or "custom"),
        (session_uri, f"{INF_NS}ontologyProfileSource", ontology_profile_source or "environment"),
        (session_uri, f"{INF_NS}ontologyFlags", json.dumps(dict(ontology_flags or {}), sort_keys=True)),
        (session_uri, f"{INF_NS}semanticCompletionStatus", completion_status),
        (session_uri, f"{INF_NS}semanticCompletionPolicy", semantic_completion_policy or "UNSPECIFIED"),
        (session_uri, f"{INF_NS}decisionLocked", str(bool(decision_locked)).lower()),
        (session_uri, f"{INF_NS}usesRuleSet", rule_uri),
        (session_uri, f"{INF_NS}ruleOntologyArtifact", rule_artifact_name(rule_name)),
        (session_uri, f"{PROV_NS}used", projection_graph_uri),
    ]
    if original_decision_name is not None:
        extra_triples.append((session_uri, f"{INF_NS}originalDecisionName", original_decision_name))
    if original_decision_value is not None:
        extra_triples.append((session_uri, f"{INF_NS}originalDecisionValue", str(original_decision_value)))
    if semantic_divergence:
        divergence_uri = f"{session_uri}/semantic-divergence/0"
        extra_triples.extend([
            (divergence_uri, RDF_TYPE, f"{INF_NS}SemanticDecisionDivergence"),
            (
                divergence_uri,
                f"{INF_NS}payload",
                json.dumps(_primitive_value(dict(semantic_divergence)), sort_keys=True, default=str),
            ),
            (divergence_uri, f"{PROV_NS}wasGeneratedBy", session_uri),
            (session_uri, f"{INF_NS}semanticDivergence", divergence_uri),
        ])

    for fact in normalized_facts:
        fact_name = str(fact["name"])
        fact_uri = f"{session_uri}/fact/{_safe_uri_component(fact_name)}"
        if fact_name == target_node_name:
            deterministic_ref = fact_uri
            extra_triples.extend([
                (session_uri, f"{INF_NS}deterministicOutcomeRef", fact_uri),
                (session_uri, f"{INF_NS}deterministicOutcomeName", fact_name),
                (session_uri, f"{INF_NS}deterministicOutcomeValue", str(fact["value"])),
                (fact_uri, f"{INF_NS}deterministicOutcome", "true"),
            ])
        extra_triples.extend([
            (fact_uri, RDF_TYPE, f"{INF_NS}CaseFact"),
            (fact_uri, f"{INF_NS}name", fact_name),
            (fact_uri, f"{INF_NS}value", str(fact["value"])),
            (fact_uri, f"{INF_NS}session", session_uri),
            (fact_uri, f"{INF_NS}rule", rule_uri),
            (fact_uri, f"{PROV_NS}wasGeneratedBy", session_uri),
        ])
        if fact_name in derived_fact_names:
            extra_triples.extend([
                (fact_uri, RDF_TYPE, f"{INF_NS}SemanticDerivedFact"),
                (fact_uri, f"{INF_NS}semanticDerived", "true"),
                (fact_uri, f"{INF_NS}authorityClass", "AUTHORITATIVE"),
                (fact_uri, f"{INF_NS}canSatisfyAuthoritativeRules", "true"),
            ])
        if fact_name in post_decision_names:
            extra_triples.extend([
                (fact_uri, f"{INF_NS}authorityClass", "AUTHORITATIVE"),
                (fact_uri, f"{INF_NS}suppliedDuring", "FULL_SEMANTIC_COMPLETION"),
                (fact_uri, f"{INF_NS}postDecisionSupplied", "true"),
                (fact_uri, f"{INF_NS}usedInOriginalDecision", "false"),
            ])
        for source in fact["sources"]:
            extra_triples.append((fact_uri, f"{INF_NS}factSource", source))

    for index, question in enumerate(deferred_question_payloads):
        question_uri = f"{session_uri}/deferred-question/{index}"
        question_name = str(question.get("question") or question.get("questionName") or "")
        node_name = str(question.get("node_name") or question.get("nodeName") or question_name)
        extra_triples.extend([
            (question_uri, RDF_TYPE, f"{INF_NS}DeferredSemanticQuestion"),
            (question_uri, f"{INF_NS}questionName", question_name),
            (question_uri, f"{INF_NS}nodeName", node_name),
            (question_uri, f"{INF_NS}resolutionRequired", "true"),
            (
                question_uri,
                f"{INF_NS}deferredDuring",
                str(question.get("deferred_during") or "FULL_SEMANTIC_TTL_GENERATION"),
            ),
            (
                question_uri,
                f"{INF_NS}payload",
                json.dumps(_primitive_value(question), sort_keys=True, default=str),
            ),
            (question_uri, f"{PROV_NS}wasGeneratedBy", session_uri),
            (session_uri, f"{INF_NS}hasDeferredQuestion", question_uri),
        ])
        reason = question.get("reason")
        if reason is not None:
            extra_triples.append((question_uri, f"{INF_NS}reason", str(reason)))

    _append_semantic_trace_triples(
        extra_triples,
        session_uri=session_uri,
        trace_name="ontology-auto-answer",
        rdf_type=f"{INF_NS}OntologyAutoAnswerTrace",
        events=ontology_auto_answer_trace or (),
    )
    _append_semantic_trace_triples(
        extra_triples,
        session_uri=session_uri,
        trace_name="ontology-materialization",
        rdf_type=f"{INF_NS}OntologyMaterializationTrace",
        events=ontology_materialization_trace or (),
    )
    _append_semantic_trace_triples(
        extra_triples,
        session_uri=session_uri,
        trace_name="semantic-question-strategy",
        rdf_type=f"{INF_NS}SemanticQuestionStrategyTrace",
        events=semantic_question_strategy_trace or (),
    )

    turtle, triple_count = _serialize_turtle([*_triples_from_payload(rule_ontology), *extra_triples])
    download_url = f"/api/v1/inference/ontology-artifact/download?session_id={quote(session_id, safe='')}"
    if ontology_profile_source == "export_override" and ontology_profile:
        download_url = f"{download_url}&ontology_profile={quote(ontology_profile, safe='')}"
    return OntologyArtifact(
        artifact_name=name,
        artifact_kind="case_run_full",
        media_type=ARTIFACT_MEDIA_TYPE,
        rule_name=rule_name,
        graph_uri=graph_uri,
        projection_graph_uri=projection_graph_uri,
        source_hash=full_source_hash,
        compiler_version=COMPILER_VERSION,
        triple_count=triple_count,
        turtle=turtle,
        artifact_uri=artifact_uri,
        download_url=download_url,
        session_id=session_id,
        case_name=case_name or session_id,
        target_node_name=target_node_name,
        deterministic_outcome_ref=deterministic_ref,
        semantic_completion_status=completion_status,
    )


def facts_from_assessment_state(assessment_state: Any) -> list[dict[str, Any]]:
    fact_store = assessment_state.get_fact_store()
    working_memory = fact_store.get_unified_view()
    facts: list[dict[str, Any]] = []
    for name, fact_value in sorted(working_memory.items()):
        try:
            sources = sorted(
                getattr(source, "value", str(source))
                for source in fact_store.get_fact_sources(name)
            )
        except Exception:
            sources = []
        facts.append({
            "name": name,
            "value": _primitive_value(fact_value),
            "sources": sources,
        })
    return facts


def _append_semantic_trace_triples(
    triples: list[tuple[str, str, str]],
    *,
    session_uri: str,
    trace_name: str,
    rdf_type: str,
    events: Sequence[Mapping[str, Any]],
) -> None:
    for index, event in enumerate(events):
        event_uri = f"{session_uri}/{trace_name}/{index}"
        triples.extend([
            (event_uri, RDF_TYPE, rdf_type),
            (event_uri, f"{INF_NS}traceKind", trace_name),
            (event_uri, f"{INF_NS}traceIndex", str(index)),
            (event_uri, f"{INF_NS}payload", json.dumps(_primitive_value(dict(event)), sort_keys=True, default=str)),
            (event_uri, f"{PROV_NS}wasGeneratedBy", session_uri),
            (session_uri, f"{INF_NS}semanticTrace", event_uri),
        ])
        for key in (
            "status",
            "action",
            "reason",
            "factName",
            "questionName",
            "nodeName",
            "sourceFactName",
            "sourceGraphUri",
            "ontologySnapshotRef",
            "ontologySnapshotHash",
            "confidence",
            "derivationRule",
            "hierarchyDepth",
            "materializedInference",
            "abstentionCause",
            "contradictionCause",
        ):
            value = event.get(key)
            if value is not None:
                triples.append((event_uri, f"{INF_NS}{_camel_case(key)}", str(value)))


def _triples_from_payload(payload: Mapping[str, Any]) -> list[tuple[str, str, str]]:
    triples = []
    for item in payload.get("triples") or []:
        if isinstance(item, Mapping):
            subject = item.get("subject")
            predicate = item.get("predicate")
            obj = item.get("object")
            if subject and predicate and obj is not None:
                triples.append((str(subject), str(predicate), str(obj)))
    return triples


def _serialize_turtle(triples: Iterable[tuple[str, str, str]]) -> tuple[str, int]:
    try:
        from rdflib import Graph, Literal, Namespace, RDF, URIRef
    except ImportError as exc:
        raise RuntimeError("rdflib is required for ontology artifact generation") from exc

    graph = Graph()
    inf = Namespace(INF_NS)
    prov = Namespace(PROV_NS)
    graph.bind("inf", inf)
    graph.bind("prov", prov)
    graph.bind("rdf", RDF)

    for subject, predicate, obj in sorted(set(triples)):
        graph.add((URIRef(subject), URIRef(predicate), _object_node(predicate, obj, URIRef, Literal)))

    result = graph.serialize(format="turtle")
    turtle = result.decode("utf-8") if isinstance(result, bytes) else str(result)
    return turtle, len(graph)


def _object_node(predicate: str, value: str, uri_ref: Any, literal: Any) -> Any:
    if predicate == RDF_TYPE or _is_uri(value):
        return uri_ref(value)
    return literal(value)


def _normalise_fact_payload(facts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in facts:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        raw_sources = item.get("sources") or []
        sources = sorted(str(source) for source in raw_sources if str(source))
        normalized.append({
            "name": name,
            "value": _primitive_value(item.get("value")),
            "sources": sources,
        })
    return sorted(normalized, key=lambda fact: fact["name"])


def _case_source_hash(
    *,
    rule_name: str,
    rule_source_hash: str,
    session_id: str,
    target_node_name: str,
    facts: Sequence[Mapping[str, Any]],
    ontology_profile: str,
    ontology_profile_source: str,
    ontology_flags: Mapping[str, Any],
    ontology_auto_answer_trace: Sequence[Mapping[str, Any]],
    ontology_materialization_trace: Sequence[Mapping[str, Any]],
    semantic_question_strategy_trace: Sequence[Mapping[str, Any]],
    ontology_derived_facts: Sequence[str],
    deferred_questions: Sequence[Mapping[str, Any]],
    post_decision_answer_names: Sequence[str],
    semantic_completion_status: str,
    semantic_completion_policy: str,
    decision_locked: bool,
    original_decision_name: str | None,
    original_decision_value: str | None,
    semantic_divergence: Mapping[str, Any],
) -> str:
    payload = {
        "compiler_version": COMPILER_VERSION,
        "decision_locked": decision_locked,
        "deferred_questions": list(deferred_questions),
        "facts": facts,
        "ontology_auto_answer_trace": list(ontology_auto_answer_trace),
        "ontology_derived_facts": list(ontology_derived_facts),
        "ontology_flags": dict(ontology_flags),
        "ontology_materialization_trace": list(ontology_materialization_trace),
        "ontology_profile": ontology_profile,
        "ontology_profile_source": ontology_profile_source,
        "original_decision_name": original_decision_name,
        "original_decision_value": original_decision_value,
        "post_decision_answer_names": list(post_decision_answer_names),
        "semantic_completion_policy": semantic_completion_policy,
        "semantic_completion_status": semantic_completion_status,
        "semantic_divergence": dict(semantic_divergence),
        "semantic_question_strategy_trace": list(semantic_question_strategy_trace),
        "rule_name": rule_name,
        "rule_source_hash": rule_source_hash,
        "session_id": session_id,
        "target_node_name": target_node_name,
    }
    return sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _artifact_stem(rule_name: str) -> str:
    stem = re.sub(r"_sections?_.+$", "", rule_name.strip(), flags=re.IGNORECASE)
    if not stem:
        stem = rule_name.strip()
    stem = re.sub(r"[^a-zA-Z0-9]+", "_", stem).strip("_").lower()
    return stem or "rule_set"


def _safe_uri_component(value: str) -> str:
    return quote(value or "unknown", safe="")


def _camel_case(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


def _is_uri(value: str) -> bool:
    return value.startswith(("http://", "https://", "urn:"))


def _primitive_value(value: Any) -> Any:
    if hasattr(value, "get_value"):
        return _primitive_value(value.get_value())
    if isinstance(value, list):
        return [_primitive_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_primitive_value(item) for item in value)
    if isinstance(value, dict):
        return {str(key): _primitive_value(item) for key, item in value.items()}
    return value

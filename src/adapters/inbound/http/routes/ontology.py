from collections import deque
from typing import Any
import hashlib
import re

from fastapi import APIRouter, Depends, HTTPException, Query
import structlog

from src.adapters.inbound.http.dependencies import require_scope
from src.adapters.inbound.http.schemas.ontology import (
    FusekiGraphListResponse,
    FusekiGraphResponse,
    OntologyChatBindingValue,
    OntologyChatGraphOverlayTargets,
    OntologyChatGuardrailReceipt,
    OntologyChatOverlayEdgeTarget,
    OntologyChatOverlayNodeTarget,
    OntologyChatQueryCandidate,
    OntologyChatQueryDetails,
    OntologyChatQueryRequest,
    OntologyChatQueryResponse,
    OntologyDecisionPathEdge,
    OntologyDecisionPathNode,
    OntologyPathResolveRequest,
    OntologyPathResolveResponse,
)
from src.adapters.outbound.ontology.fuseki_adapter import (
    INF_NS,
    FusekiAdapter,
    FusekiConnectionError,
)
from src.services.ontology_chat_planner import plan_ontology_chat_query


router = APIRouter(prefix="/api/v1/ontology", tags=["ontology"])
log = structlog.get_logger(__name__)

RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
PROV_NS = "http://www.w3.org/ns/prov#"
MAX_CHAT_QUERY_LENGTH = 6000
PATH_SELECT_TIMEOUT_SECONDS = 10
PATH_SELECT_MAX_RETRIES = 0
PATH_RESULT_LIMIT = 25000
UNSAFE_SPARQL_TOKENS = {
    "ADD",
    "CLEAR",
    "COPY",
    "CREATE",
    "DELETE",
    "DROP",
    "INSERT",
    "LOAD",
    "MOVE",
    "SERVICE",
    "USING",
    "WITH",
}
FULL_SEMANTIC_GRAPH_HINTS = (
    "/full-semantic/",
    "#case-run/",
    "/case-run/",
    "#artifact/full/",
)
PROJECTION_GRAPH_HINTS = ("#projection/rule/", "/projection/rule/")
DEPENDENCY_PREDICATE_URIS = (
    f"{INF_NS}dependsOn",
    f"{INF_NS}andDependsOn",
    f"{INF_NS}orDependsOn",
    f"{INF_NS}notDependsOn",
    f"{INF_NS}knownDependsOn",
    f"{INF_NS}mandatoryDependsOn",
    f"{INF_NS}optionalDependsOn",
    f"{INF_NS}possibleDependsOn",
    f"{INF_NS}iteratesOver",
    f"{INF_NS}requiresVariable",
)
STRUCTURAL_PREDICATE_URIS = (
    *DEPENDENCY_PREDICATE_URIS,
    f"{INF_NS}dependencyProperty",
    f"{INF_NS}comparesTo",
)
TRACE_TYPE_URIS = (
    f"{INF_NS}SemanticQuestionStrategyTrace",
    f"{INF_NS}OntologyAutoAnswerTrace",
    f"{INF_NS}OntologyMaterializationTrace",
)
ROW_URI_PRIORITY = (
    "fact",
    "selected",
    "selectedUri",
    "subject",
    "s",
    "node",
    "caseFact",
    "caseRun",
    "trace",
    "strategy",
    "object",
    "o",
    "target",
)
ROW_LABEL_PRIORITY = (
    "questionName",
    "factName",
    "name",
    "nodeName",
    "relatedNodeName",
    "targetNodeName",
    "label",
    "value",
    "caseName",
)


@router.get(
    "/fuseki/graphs",
    response_model=FusekiGraphListResponse,
    dependencies=[Depends(require_scope("read"))],
)
async def list_fuseki_named_graphs() -> FusekiGraphListResponse:
    graphs = [
        {"uri": uri, "triple_count": triple_count}
        for uri, triple_count in FusekiAdapter.list_named_graphs()
    ]
    return FusekiGraphListResponse(graphs=graphs, total_count=len(graphs))


@router.get(
    "/fuseki/graph",
    response_model=FusekiGraphResponse,
    dependencies=[Depends(require_scope("read"))],
)
async def get_fuseki_named_graph(
    graph_uri: str = Query(..., min_length=1),
    offset: int = Query(0, ge=0),
    limit: int = Query(1000, ge=1, le=5000),
) -> FusekiGraphResponse:
    resolved_graph_uri = _resolve_latest_full_semantic_pointer(graph_uri)
    triples = FusekiAdapter.get_named_graph_triples(resolved_graph_uri, offset=offset, limit=limit)
    graph = _ontology_graph_from_triples(triples)
    return FusekiGraphResponse(
        graph_uri=resolved_graph_uri,
        triple_count=len(triples),
        triples=[
            {"subject": subject, "predicate": predicate, "object": obj}
            for subject, predicate, obj in triples
        ],
        nodes=graph["nodes"],
        edges=graph["edges"],
        offset=offset,
        limit=limit,
    )


@router.post(
    "/chat/query",
    response_model=OntologyChatQueryResponse,
    dependencies=[Depends(require_scope("read"))],
)
async def query_ontology_chat(
    request: OntologyChatQueryRequest,
) -> OntologyChatQueryResponse:
    available_graphs = _list_available_graphs()
    selected_graphs = _validate_selected_graphs(
        request.selected_graph_uris,
        available_graphs,
    )
    candidate = request.candidate
    if candidate is None:
        plan = plan_ontology_chat_query(
            question=request.question,
            selected_graphs=selected_graphs,
            graph_counts=available_graphs,
            row_limit=request.row_limit,
            timeout_seconds=request.timeout_seconds,
        )
        candidate = OntologyChatQueryCandidate.model_validate(
            plan.as_candidate_payload()
        )

    if candidate and candidate.status == "abstain":
        receipt = _guardrail_receipt(
            selected_graphs=selected_graphs,
            available_graph_count=len(available_graphs),
            query_length=0,
            row_limit=request.row_limit,
            timeout_seconds=request.timeout_seconds,
            max_retries=request.max_retries,
            read_only=True,
            graph_scope_validated=True,
            checks={
                "structured_contract_received": True,
                "llm_abstained": True,
                "fuseki_executed": False,
            },
        )
        return OntologyChatQueryResponse(
            status="abstained",
            question=request.question,
            query_details=OntologyChatQueryDetails(
                source="abstained",
                contract_version=candidate.contract_version,
                sparql=None,
                rationale=candidate.rationale,
                validation_status="abstained",
                selected_graph_uris=selected_graphs,
                result_limit=request.row_limit,
                timeout_seconds=request.timeout_seconds,
            ),
            rows=[],
            overlay_targets={
                graph_uri: OntologyChatGraphOverlayTargets()
                for graph_uri in selected_graphs
            },
            guardrail_receipt=receipt,
            provenance=_chat_provenance(
                "structured_candidate",
                executed=False,
                candidate_provenance=candidate.provenance if candidate else None,
            ),
        )

    sparql, query_source, contract_version, rationale = _resolve_chat_sparql(
        request,
        selected_graphs,
        candidate=candidate,
    )
    receipt = _guardrail_receipt(
        selected_graphs=selected_graphs,
        available_graph_count=len(available_graphs),
        query_length=len(sparql),
        row_limit=request.row_limit,
        timeout_seconds=request.timeout_seconds,
        max_retries=request.max_retries,
    )
    _validate_guarded_sparql(
        sparql,
        selected_graphs=selected_graphs,
        row_limit=request.row_limit,
        receipt=receipt,
    )
    receipt.read_only = True
    receipt.graph_scope_validated = True
    receipt.checks.update(
        {
            "query_length_within_limit": True,
            "read_only_select": True,
            "remote_service_blocked": True,
            "graph_scope_validated": True,
            "limit_within_row_cap": True,
            "fuseki_executed": True,
        }
    )
    log.warning(
        "ontology_chat_sparql_executing",
        question_hash=hashlib.sha256(request.question.encode("utf-8")).hexdigest(),
        selected_graphs=selected_graphs,
        query_source=query_source,
        contract_version=contract_version,
        row_limit=request.row_limit,
        timeout_seconds=request.timeout_seconds,
        sparql=sparql,
    )

    try:
        raw_bindings = FusekiAdapter.execute_guarded_select(
            sparql,
            timeout_seconds=request.timeout_seconds,
            max_retries=request.max_retries,
        )
    except FusekiConnectionError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "fuseki_query_failed",
                "message": str(exc),
                "guardrail_receipt": receipt.model_dump(),
            },
        ) from exc

    capped_bindings = raw_bindings[: request.row_limit]
    receipt.result_cap_applied = len(raw_bindings) > len(capped_bindings)
    rows = _rows_from_bindings(capped_bindings)

    return OntologyChatQueryResponse(
        status="ok",
        question=request.question,
        query_details=OntologyChatQueryDetails(
            source=query_source,
            contract_version=contract_version,
            sparql=sparql,
            rationale=rationale,
            validation_status="validated",
            selected_graph_uris=selected_graphs,
            result_limit=request.row_limit,
            timeout_seconds=request.timeout_seconds,
        ),
        rows=rows,
        overlay_targets=_overlay_targets(rows, selected_graphs),
        guardrail_receipt=receipt,
        provenance=_chat_provenance(
            query_source,
            executed=True,
            candidate_provenance=candidate.provenance if candidate else None,
        ),
    )


@router.post(
    "/path/resolve",
    response_model=OntologyPathResolveResponse,
    dependencies=[Depends(require_scope("read"))],
)
async def resolve_ontology_decision_path(
    request: OntologyPathResolveRequest,
) -> OntologyPathResolveResponse:
    available_graphs = _list_available_graphs()
    selected_graphs = _validate_selected_graphs(
        request.selected_graph_uris,
        available_graphs,
    )
    if request.active_graph_uri:
        _validate_chat_graph_uri(request.active_graph_uri)

    warnings: list[str] = []
    authoritative_graphs = _authoritative_full_semantic_graphs(
        selected_graphs,
        warnings,
    )
    structural_graphs = [
        graph_uri for graph_uri in selected_graphs if _is_projection_graph(graph_uri)
    ]
    if not structural_graphs:
        structural_graphs = list(authoritative_graphs)

    try:
        context = _load_decision_path_context(
            authoritative_graphs,
            structural_graphs,
        )
    except FusekiConnectionError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "fuseki_path_query_failed",
                "message": str(exc),
            },
        ) from exc

    response = _resolve_decision_path(
        request=request,
        authoritative_graphs=authoritative_graphs,
        structural_graphs=structural_graphs,
        context=context,
        warnings=warnings,
    )
    log.info(
        "ontology_decision_path_resolved",
        selected_graph_count=len(selected_graphs),
        authoritative_graph_count=len(authoritative_graphs),
        structural_graph_count=len(structural_graphs),
        selected_uri=response.selected_uri,
        target_uri=response.target_uri,
        node_count=len(response.nodes),
        edge_count=len(response.edges),
        status=response.status,
    )
    return response


def _ontology_graph_from_triples(triples: list[tuple[str, str, str]]) -> dict:
    node_map: dict[str, dict] = {}
    edges: list[dict[str, str]] = []

    def ensure_node(uri: str) -> dict:
        return node_map.setdefault(uri, {"uri": uri, "name": None, "types": []})

    for subject, predicate, obj in triples:
        ensure_node(subject)
        if predicate == f"{INF_NS}name":
            node_map[subject]["name"] = obj
            continue
        if predicate == RDF_TYPE:
            node = ensure_node(subject)
            if obj not in node["types"]:
                node["types"].append(obj)
            continue
        if obj.startswith(("http://", "https://", "urn:")):
            ensure_node(obj)
            edges.append({"subject": subject, "predicate": predicate, "object": obj})

    return {"nodes": list(node_map.values()), "edges": edges}


def _authoritative_full_semantic_graphs(
    selected_graphs: list[str],
    warnings: list[str],
) -> list[str]:
    authoritative = [
        graph_uri for graph_uri in selected_graphs if _is_full_semantic_graph(graph_uri)
    ]
    if authoritative:
        return authoritative

    fallback = [graph_uri for graph_uri in selected_graphs if not _is_projection_graph(graph_uri)]
    if fallback:
        warnings.append(
            "No selected graph URI was recognisable as a Full Semantic graph; "
            "using selected non-projection graph(s) as authoritative candidates."
        )
        return fallback

    warnings.append(
        "Select a Full Semantic graph to resolve an authoritative case decision path."
    )
    return []


def _is_full_semantic_graph(graph_uri: str) -> bool:
    lowered = graph_uri.lower()
    return any(hint in lowered for hint in FULL_SEMANTIC_GRAPH_HINTS)


def _is_projection_graph(graph_uri: str) -> bool:
    lowered = graph_uri.lower()
    return any(hint in lowered for hint in PROJECTION_GRAPH_HINTS)


def _resolve_latest_full_semantic_pointer(graph_uri: str) -> str:
    if not graph_uri.lower().endswith("/latest"):
        return graph_uri
    try:
        rows = FusekiAdapter.execute_guarded_select(
            (
                "PREFIX inf: <http://inferra.ai/schema#> "
                "SELECT ?version WHERE { "
                f"GRAPH <{graph_uri}> {{ <{graph_uri}> inf:latestVersionGraph ?version . }} "
                "} LIMIT 1"
            ),
            timeout_seconds=5,
            max_retries=0,
        )
    except Exception:
        return graph_uri
    if not rows:
        return graph_uri
    value = rows[0].get("version", {}).get("value")
    return str(value) if value else graph_uri


def _load_decision_path_context(
    authoritative_graphs: list[str],
    structural_graphs: list[str],
) -> dict[str, Any]:
    context: dict[str, Any] = {
        "case_runs": [],
        "case_runs_by_uri": {},
        "facts_by_uri": {},
        "facts_by_name": {},
        "traces_by_uri": {},
        "traces_by_name": {},
        "projection_nodes_by_uri": {},
        "projection_nodes_by_name": {},
        "projection_edges": [],
        "projection_node_limit_hit": False,
        "projection_edge_limit_hit": False,
    }
    if authoritative_graphs:
        _load_case_run_context(authoritative_graphs, context)
        _load_trace_context(authoritative_graphs, context)
    if structural_graphs:
        _load_projection_context(structural_graphs, context)
    return context


def _load_case_run_context(graphs: list[str], context: dict[str, Any]) -> None:
    for binding in _execute_path_select(_case_run_context_sparql(graphs)):
        graph_uri = _binding_value(binding, "graph")
        case_run_uri = _binding_value(binding, "caseRun")
        if graph_uri and case_run_uri:
            case_run = context["case_runs_by_uri"].setdefault(
                case_run_uri,
                {
                    "uri": case_run_uri,
                    "graph_uri": graph_uri,
                    "case_name": None,
                    "rule_name": None,
                    "target_node_name": None,
                    "deterministic_outcome_ref": None,
                    "deterministic_outcome_name": None,
                    "deterministic_outcome_value": None,
                },
            )
            for source, target in (
                ("caseName", "case_name"),
                ("ruleName", "rule_name"),
                ("targetNodeName", "target_node_name"),
                ("deterministicOutcomeRef", "deterministic_outcome_ref"),
                ("deterministicOutcomeName", "deterministic_outcome_name"),
                ("deterministicOutcomeValue", "deterministic_outcome_value"),
            ):
                value = _binding_value(binding, source)
                if value is not None:
                    case_run[target] = value

        fact_uri = _binding_value(binding, "fact")
        fact_name = _binding_value(binding, "factName")
        if graph_uri and fact_uri and fact_name:
            fact = context["facts_by_uri"].setdefault(
                fact_uri,
                {
                    "uri": fact_uri,
                    "graph_uri": graph_uri,
                    "name": fact_name,
                    "value": None,
                    "sources": set(),
                    "session_uri": None,
                },
            )
            fact["name"] = fact_name
            value = _binding_value(binding, "factValue")
            if value is not None:
                fact["value"] = value
            source = _binding_value(binding, "factSource")
            if source:
                fact["sources"].add(source)
            session_uri = _binding_value(binding, "factSession") or case_run_uri
            if session_uri:
                fact["session_uri"] = session_uri
            _index_by_normalized_name(context["facts_by_name"], fact_name, fact)

    context["case_runs"] = list(context["case_runs_by_uri"].values())
    for fact in context["facts_by_uri"].values():
        fact["sources"] = sorted(fact["sources"])


def _load_trace_context(graphs: list[str], context: dict[str, Any]) -> None:
    for binding in _execute_path_select(_trace_context_sparql(graphs)):
        graph_uri = _binding_value(binding, "graph")
        trace_uri = _binding_value(binding, "trace")
        if not graph_uri or not trace_uri:
            continue
        trace = context["traces_by_uri"].setdefault(
            trace_uri,
            {
                "uri": trace_uri,
                "graph_uri": graph_uri,
                "trace_type": None,
                "trace_kind": None,
                "question_name": None,
                "node_name": None,
                "fact_name": None,
                "source_fact_name": None,
                "status": None,
                "action": None,
                "reason": None,
                "generated_by": None,
            },
        )
        for source, target in (
            ("traceType", "trace_type"),
            ("traceKind", "trace_kind"),
            ("questionName", "question_name"),
            ("nodeName", "node_name"),
            ("factName", "fact_name"),
            ("sourceFactName", "source_fact_name"),
            ("status", "status"),
            ("action", "action"),
            ("reason", "reason"),
            ("generatedBy", "generated_by"),
        ):
            value = _binding_value(binding, source)
            if value is not None:
                trace[target] = value
        for label in _trace_labels(trace):
            _index_by_normalized_name(context["traces_by_name"], label, trace)


def _load_projection_context(graphs: list[str], context: dict[str, Any]) -> None:
    node_bindings = _execute_path_select(_projection_nodes_sparql(graphs))
    if len(node_bindings) >= PATH_RESULT_LIMIT:
        context["projection_node_limit_hit"] = True
    for binding in node_bindings:
        graph_uri = _binding_value(binding, "graph")
        node_uri = _binding_value(binding, "node")
        name = _binding_value(binding, "name")
        if not graph_uri or not node_uri or not name:
            continue
        node = context["projection_nodes_by_uri"].setdefault(
            node_uri,
            {
                "uri": node_uri,
                "graph_uri": graph_uri,
                "name": name,
                "types": set(),
            },
        )
        node["name"] = name
        node_type = _binding_value(binding, "type")
        if node_type:
            node["types"].add(node_type)
        _index_by_normalized_name(context["projection_nodes_by_name"], name, node)

    for node in context["projection_nodes_by_uri"].values():
        node["types"] = sorted(node["types"])

    edge_bindings = _execute_path_select(_projection_edges_sparql(graphs))
    if len(edge_bindings) >= PATH_RESULT_LIMIT:
        context["projection_edge_limit_hit"] = True
    for binding in edge_bindings:
        graph_uri = _binding_value(binding, "graph")
        source_uri = _binding_value(binding, "source")
        predicate_uri = _binding_value(binding, "predicate")
        target_uri = _binding_value(binding, "target")
        if graph_uri and source_uri and predicate_uri and target_uri:
            context["projection_edges"].append(
                {
                    "graph_uri": graph_uri,
                    "source_uri": source_uri,
                    "predicate_uri": predicate_uri,
                    "target_uri": target_uri,
                }
            )


def _resolve_decision_path(
    *,
    request: OntologyPathResolveRequest,
    authoritative_graphs: list[str],
    structural_graphs: list[str],
    context: dict[str, Any],
    warnings: list[str],
) -> OntologyPathResolveResponse:
    nodes: dict[str, OntologyDecisionPathNode] = {}
    edges: dict[str, OntologyDecisionPathEdge] = {}
    selected_uri = _selected_uri_from_request(request)
    selected_label = _selected_label_from_request(request)
    selected_graph_hint = request.active_graph_uri or (request.selected_graph_uris[0] if request.selected_graph_uris else "")
    case_run = _preferred_case_run(context["case_runs"], request.active_graph_uri)
    target_name = _case_run_target_name(case_run)
    target_uri = _target_uri(case_run, target_name, context)

    selected_fact = _match_item(
        selected_uri,
        selected_label,
        context["facts_by_uri"],
        context["facts_by_name"],
    )
    selected_trace = _match_item(
        selected_uri,
        selected_label,
        context["traces_by_uri"],
        context["traces_by_name"],
    )
    selected_projection = _match_item(
        selected_uri,
        selected_label,
        context["projection_nodes_by_uri"],
        context["projection_nodes_by_name"],
    )
    selected_case_run = context["case_runs_by_uri"].get(selected_uri) if selected_uri else None

    if selected_fact:
        selected_uri = selected_fact["uri"]
        selected_label = selected_fact["name"]
        _add_path_node(
            nodes,
            selected_fact["uri"],
            selected_fact["name"],
            selected_fact["graph_uri"],
            role="selected",
            match_kind="exact_uri" if request.selected_uri == selected_fact["uri"] else "exact_normalized_label",
        )
    elif selected_trace:
        selected_uri = selected_trace["uri"]
        selected_label = _trace_display_label(selected_trace)
        _add_path_node(
            nodes,
            selected_trace["uri"],
            selected_label,
            selected_trace["graph_uri"],
            role="selected",
            match_kind="exact_uri" if request.selected_uri == selected_trace["uri"] else "trace_normalized_label",
        )
    elif selected_projection:
        selected_uri = selected_projection["uri"]
        selected_label = selected_projection["name"]
        _add_path_node(
            nodes,
            selected_projection["uri"],
            selected_projection["name"],
            selected_projection["graph_uri"],
            role="selected",
            match_kind="exact_uri" if request.selected_uri == selected_projection["uri"] else "projection_normalized_label",
        )
    elif selected_case_run:
        selected_uri = selected_case_run["uri"]
        selected_label = selected_case_run.get("case_name") or _short_uri(selected_case_run["uri"])
        _add_path_node(
            nodes,
            selected_case_run["uri"],
            selected_label,
            selected_case_run["graph_uri"],
            role="selected",
            match_kind="exact_uri",
        )
    elif selected_uri:
        _add_path_node(
            nodes,
            selected_uri,
            selected_label or _short_uri(selected_uri),
            selected_graph_hint,
            role="selected",
            match_kind="exact_uri",
        )
        warnings.append(
            "The selected URI was not found as a CaseFact, CaseRun, semantic trace, or projection node in the selected graphs."
        )
    elif selected_label:
        warnings.append(
            "No exact normalized graph item matched the selected result label."
        )
    else:
        warnings.append("Select a result row or graph node to resolve a decision path.")

    if target_uri and target_name:
        target_graph = _target_graph_uri(target_uri, case_run, context)
        _add_path_node(
            nodes,
            target_uri,
            target_name,
            target_graph,
            role="conclusion",
            match_kind="target_conclusion",
        )
    elif target_name:
        warnings.append(
            "The CaseRun target node name was found, but no matching deterministic outcome URI or CaseFact URI was available."
        )
    else:
        warnings.append(
            "No CaseRun target node name was available in the selected Full Semantic graph."
        )

    if selected_fact:
        _append_fact_authoritative_path(
            selected_fact,
            case_run,
            target_uri,
            nodes,
            edges,
        )
        _append_matching_traces(
            selected_fact,
            selected_label,
            case_run,
            context,
            nodes,
            edges,
        )
    elif selected_trace:
        _append_trace_authoritative_path(
            selected_trace,
            case_run,
            target_uri,
            nodes,
            edges,
        )
    elif selected_case_run and target_uri:
        _append_case_run_target_edge(
            selected_case_run,
            target_uri,
            target_name,
            nodes,
            edges,
        )

    projection_start = selected_projection or _projection_node_for_selected_item(
        selected_fact,
        selected_trace,
        selected_label,
        context,
    )
    projection_target = _projection_node_for_labels([target_name], context)
    if structural_graphs and projection_start and projection_target:
        path_edges = _projection_bfs(
            projection_start["uri"],
            projection_target["uri"],
            context["projection_edges"],
            max_depth=request.max_depth,
        )
        if path_edges is None:
            warnings.append(
                _structural_no_path_warning(
                    structural_graphs=structural_graphs,
                    existing_edges=bool(edges),
                    max_depth=request.max_depth,
                    context=context,
                    projection_start=projection_start,
                    projection_target=projection_target,
                )
            )
        else:
            _append_projection_path(
                path_edges,
                projection_start,
                projection_target,
                selected_uri,
                target_uri,
                context,
                nodes,
                edges,
            )
    elif not structural_graphs:
        warnings.append(
            "No Rule Projection graph is selected; structural dependency path highlighting is limited to authoritative case-run relationships."
        )
    elif not projection_start:
        warnings.append(
            "No exact normalized projection-node match was found for the selected item."
        )
    elif not projection_target:
        warnings.append(
            "No exact normalized projection-node match was found for the CaseRun target node."
        )

    path_nodes = list(nodes.values())
    path_edges = _ordered_edges(edges.values(), request.direction)
    status = "ok" if selected_uri and target_uri and (path_edges or selected_uri == target_uri) else "no_path"
    if status == "no_path" and selected_uri and target_uri:
        warnings.append(
            "The selected item and target were identified, but no explicit path edge was found in the selected graph set."
        )

    return OntologyPathResolveResponse(
        status=status,
        selected_uri=selected_uri,
        selected_label=selected_label,
        target_uri=target_uri,
        target_node_name=target_name,
        authoritative_graph_uris=authoritative_graphs,
        structural_graph_uris=structural_graphs,
        nodes=path_nodes,
        edges=path_edges,
        relationship_summary=_relationship_summary(path_edges),
        warnings=_unique_stable(warnings),
        provenance={
            "resolver": "ontology-decision-path-v1",
            "authoritative_source": "Full Semantic graph",
            "structural_reference": "Rule Projection graph when selected",
            "selected_row_index": request.selected_row_index,
            "match_policy": "exact URI first, then exact normalized label",
            "direction": request.direction,
            "max_depth": request.max_depth,
        },
    )


def _append_fact_authoritative_path(
    selected_fact: dict[str, Any],
    case_run: dict[str, Any] | None,
    target_uri: str | None,
    nodes: dict[str, OntologyDecisionPathNode],
    edges: dict[str, OntologyDecisionPathEdge],
) -> None:
    session_uri = selected_fact.get("session_uri") or (case_run or {}).get("uri")
    if session_uri:
        _add_path_node(
            nodes,
            session_uri,
            (case_run or {}).get("case_name") or _short_uri(session_uri),
            selected_fact["graph_uri"],
            role="case_run",
            match_kind="related",
        )
        _add_path_edge(
            edges,
            selected_fact["uri"],
            f"{INF_NS}session",
            session_uri,
            selected_fact["graph_uri"],
            relationship_type="authoritative_case_fact",
            direction="evidence_to_conclusion",
        )
    if case_run and target_uri:
        _append_case_run_target_edge(case_run, target_uri, None, nodes, edges)


def _append_matching_traces(
    selected_fact: dict[str, Any],
    selected_label: str | None,
    case_run: dict[str, Any] | None,
    context: dict[str, Any],
    nodes: dict[str, OntologyDecisionPathNode],
    edges: dict[str, OntologyDecisionPathEdge],
) -> None:
    labels = [selected_fact.get("name"), selected_label]
    matching_traces = _traces_for_labels(labels, context)[:8]
    session_uri = selected_fact.get("session_uri") or (case_run or {}).get("uri")
    for trace in matching_traces:
        _add_path_node(
            nodes,
            trace["uri"],
            _trace_display_label(trace),
            trace["graph_uri"],
            role="trace",
            match_kind="trace_normalized_label",
        )
        generated_by = trace.get("generated_by") or session_uri
        if generated_by:
            _add_path_edge(
                edges,
                generated_by,
                f"{INF_NS}semanticTrace",
                trace["uri"],
                trace["graph_uri"],
                relationship_type="semantic_trace",
                direction="evidence_to_conclusion",
            )


def _append_trace_authoritative_path(
    selected_trace: dict[str, Any],
    case_run: dict[str, Any] | None,
    target_uri: str | None,
    nodes: dict[str, OntologyDecisionPathNode],
    edges: dict[str, OntologyDecisionPathEdge],
) -> None:
    generated_by = selected_trace.get("generated_by") or (case_run or {}).get("uri")
    if generated_by:
        _add_path_node(
            nodes,
            generated_by,
            (case_run or {}).get("case_name") or _short_uri(generated_by),
            selected_trace["graph_uri"],
            role="case_run",
            match_kind="related",
        )
        _add_path_edge(
            edges,
            generated_by,
            f"{INF_NS}semanticTrace",
            selected_trace["uri"],
            selected_trace["graph_uri"],
            relationship_type="semantic_trace",
            direction="evidence_to_conclusion",
        )
    if case_run and target_uri:
        _append_case_run_target_edge(case_run, target_uri, None, nodes, edges)


def _append_case_run_target_edge(
    case_run: dict[str, Any],
    target_uri: str,
    target_name: str | None,
    nodes: dict[str, OntologyDecisionPathNode],
    edges: dict[str, OntologyDecisionPathEdge],
) -> None:
    _add_path_node(
        nodes,
        case_run["uri"],
        case_run.get("case_name") or _short_uri(case_run["uri"]),
        case_run["graph_uri"],
        role="case_run",
        match_kind="related",
    )
    _add_path_node(
        nodes,
        target_uri,
        target_name or case_run.get("deterministic_outcome_name") or _short_uri(target_uri),
        case_run["graph_uri"],
        role="conclusion",
        match_kind="target_conclusion",
    )
    _add_path_edge(
        edges,
        case_run["uri"],
        f"{INF_NS}deterministicOutcomeRef",
        target_uri,
        case_run["graph_uri"],
        relationship_type="authoritative_outcome",
        direction="evidence_to_conclusion",
    )


def _append_projection_path(
    path_edges: list[dict[str, str]],
    projection_start: dict[str, Any],
    projection_target: dict[str, Any],
    selected_uri: str | None,
    target_uri: str | None,
    context: dict[str, Any],
    nodes: dict[str, OntologyDecisionPathNode],
    edges: dict[str, OntologyDecisionPathEdge],
) -> None:
    _add_projection_node(projection_start, nodes, match_kind="structural_reference")
    _add_projection_node(projection_target, nodes, match_kind="structural_reference")
    if selected_uri and selected_uri != projection_start["uri"]:
        _add_path_edge(
            edges,
            selected_uri,
            f"{INF_NS}structuralReference",
            projection_start["uri"],
            projection_start["graph_uri"],
            relationship_type="soft_match",
            direction="bidirectional",
        )
    for edge in path_edges:
        source = context["projection_nodes_by_uri"].get(edge["source_uri"])
        target = context["projection_nodes_by_uri"].get(edge["target_uri"])
        if source:
            _add_projection_node(source, nodes, match_kind="structural_reference")
        if target:
            _add_projection_node(target, nodes, match_kind="structural_reference")
        _add_path_edge(
            edges,
            edge["source_uri"],
            edge["predicate_uri"],
            edge["target_uri"],
            edge["graph_uri"],
            relationship_type=(
                "projection_dependency"
                if edge["predicate_uri"] in DEPENDENCY_PREDICATE_URIS
                else "projection_structure"
            ),
            direction="bidirectional",
        )
    if target_uri and target_uri != projection_target["uri"]:
        _add_path_edge(
            edges,
            projection_target["uri"],
            f"{INF_NS}authoritativeOutcomeRef",
            target_uri,
            projection_target["graph_uri"],
            relationship_type="soft_match",
            direction="bidirectional",
        )


def _add_projection_node(
    node: dict[str, Any],
    nodes: dict[str, OntologyDecisionPathNode],
    *,
    match_kind: str,
) -> None:
    _add_path_node(
        nodes,
        node["uri"],
        node["name"],
        node["graph_uri"],
        role="projection_node",
        match_kind=match_kind,
    )


def _projection_node_for_selected_item(
    selected_fact: dict[str, Any] | None,
    selected_trace: dict[str, Any] | None,
    selected_label: str | None,
    context: dict[str, Any],
) -> dict[str, Any] | None:
    labels: list[str | None] = [selected_label]
    if selected_fact:
        labels.extend([selected_fact.get("name")])
    if selected_trace:
        labels.extend(_trace_labels(selected_trace))
    return _projection_node_for_labels(labels, context)


def _projection_node_for_labels(
    labels: list[str | None],
    context: dict[str, Any],
) -> dict[str, Any] | None:
    for label in labels:
        normalized = _normalize_label(label)
        if not normalized:
            continue
        matches = context["projection_nodes_by_name"].get(normalized, [])
        if matches:
            return matches[0]
    return None


def _structural_source_label(structural_graphs: list[str]) -> str:
    if any(_is_projection_graph(graph_uri) for graph_uri in structural_graphs):
        return "Rule Projection"
    return "Full Semantic structural"


def _structural_no_path_warning(
    *,
    structural_graphs: list[str],
    existing_edges: bool,
    max_depth: int,
    context: dict[str, Any],
    projection_start: dict[str, Any],
    projection_target: dict[str, Any],
) -> str:
    source_label = _structural_source_label(structural_graphs)
    prefix = (
        f"The authoritative case relationship was resolved, but no additional {source_label} path "
        if existing_edges
        else f"A selected {source_label} graph was available, but no structural path "
    )
    detail = (
        f"connected '{projection_start.get('name')}' to target '{projection_target.get('name')}' "
        f"within depth {max_depth}."
    )
    if context.get("projection_edge_limit_hit") or context.get("projection_node_limit_hit"):
        return (
            f"{prefix}{detail} The structural graph query reached the {PATH_RESULT_LIMIT}-row cap, "
            "so the relevant rule edge may not have been loaded."
        )
    return (
        f"{prefix}{detail} This usually means the selected row is not on the target decision branch, "
        "or the selected result value matched a projection node outside the target's rule dependency component."
    )


def _projection_bfs(
    start_uri: str,
    target_uri: str,
    projection_edges: list[dict[str, str]],
    *,
    max_depth: int,
) -> list[dict[str, str]] | None:
    if start_uri == target_uri:
        return []
    adjacency: dict[str, list[tuple[str, dict[str, str]]]] = {}
    for edge in projection_edges:
        adjacency.setdefault(edge["source_uri"], []).append((edge["target_uri"], edge))
        adjacency.setdefault(edge["target_uri"], []).append((edge["source_uri"], edge))

    queue: deque[tuple[str, list[dict[str, str]]]] = deque([(start_uri, [])])
    visited = {start_uri}
    while queue:
        uri, path = queue.popleft()
        if len(path) >= max_depth:
            continue
        for next_uri, edge in adjacency.get(uri, []):
            if next_uri in visited:
                continue
            next_path = [*path, edge]
            if next_uri == target_uri:
                return next_path
            visited.add(next_uri)
            queue.append((next_uri, next_path))
    return None


def _add_path_node(
    nodes: dict[str, OntologyDecisionPathNode],
    uri: str,
    label: str,
    graph_uri: str,
    *,
    role: str,
    match_kind: str,
) -> None:
    if not uri:
        return
    existing = nodes.get(uri)
    if existing and _role_priority(existing.role) > _role_priority(role):
        return
    nodes[uri] = OntologyDecisionPathNode(
        uri=uri,
        label=label or _short_uri(uri),
        graph_uri=graph_uri,
        role=role,
        match_kind=match_kind,
    )


def _add_path_edge(
    edges: dict[str, OntologyDecisionPathEdge],
    source_uri: str,
    predicate_uri: str,
    target_uri: str,
    graph_uri: str,
    *,
    relationship_type: str,
    direction: str,
) -> None:
    if not source_uri or not predicate_uri or not target_uri:
        return
    key = f"{graph_uri}|{source_uri}|{predicate_uri}|{target_uri}"
    edges[key] = OntologyDecisionPathEdge(
        source_uri=source_uri,
        predicate_uri=predicate_uri,
        target_uri=target_uri,
        label=_predicate_label(predicate_uri),
        graph_uri=graph_uri,
        relationship_type=relationship_type,
        direction=direction,
    )


def _role_priority(role: str) -> int:
    return {
        "unknown": 0,
        "projection_node": 1,
        "trace": 2,
        "case_run": 2,
        "fact": 3,
        "conclusion": 4,
        "selected": 5,
    }.get(role, 0)


def _ordered_edges(
    edges: list[OntologyDecisionPathEdge],
    direction: str,
) -> list[OntologyDecisionPathEdge]:
    if direction == "conclusion_to_evidence":
        return list(reversed(sorted(edges, key=_edge_sort_key)))
    return sorted(edges, key=_edge_sort_key)


def _edge_sort_key(edge: OntologyDecisionPathEdge) -> tuple[int, str, str, str]:
    relationship_order = {
        "authoritative_case_fact": 0,
        "semantic_trace": 1,
        "projection_structure": 2,
        "projection_dependency": 3,
        "soft_match": 4,
        "authoritative_outcome": 5,
    }
    return (
        relationship_order.get(edge.relationship_type, 9),
        edge.graph_uri,
        edge.source_uri,
        edge.target_uri,
    )


def _relationship_summary(edges: list[OntologyDecisionPathEdge]) -> list[str]:
    return [
        f"{_short_uri(edge.source_uri)} --{edge.label}--> {_short_uri(edge.target_uri)} ({edge.relationship_type})"
        for edge in edges[:18]
    ]


def _selected_uri_from_request(request: OntologyPathResolveRequest) -> str | None:
    if _is_absolute_uri(request.selected_uri):
        return request.selected_uri.strip()
    row = request.selected_row or {}
    for name in ROW_URI_PRIORITY:
        value = row.get(name)
        if value and value.type == "uri" and _is_absolute_uri(value.value):
            return value.value.strip()
    for value in row.values():
        if value and value.type == "uri" and _is_absolute_uri(value.value):
            return value.value.strip()
    return None


def _selected_label_from_request(request: OntologyPathResolveRequest) -> str | None:
    if request.selected_label and request.selected_label.strip():
        return request.selected_label.strip()
    row = request.selected_row or {}
    for name in ROW_LABEL_PRIORITY:
        value = row.get(name)
        if value and value.value.strip():
            return value.value.strip()
    return None


def _match_item(
    selected_uri: str | None,
    selected_label: str | None,
    by_uri: dict[str, dict[str, Any]],
    by_name: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    if selected_uri and selected_uri in by_uri:
        return by_uri[selected_uri]
    normalized = _normalize_label(selected_label)
    if normalized:
        matches = by_name.get(normalized, [])
        if matches:
            return matches[0]
    return None


def _preferred_case_run(
    case_runs: list[dict[str, Any]],
    active_graph_uri: str | None,
) -> dict[str, Any] | None:
    if not case_runs:
        return None
    if active_graph_uri:
        for case_run in case_runs:
            if case_run.get("graph_uri") == active_graph_uri:
                return case_run
    return sorted(case_runs, key=lambda item: (item.get("graph_uri") or "", item.get("uri") or ""))[0]


def _case_run_target_name(case_run: dict[str, Any] | None) -> str | None:
    if not case_run:
        return None
    return case_run.get("target_node_name") or case_run.get("deterministic_outcome_name")


def _target_uri(
    case_run: dict[str, Any] | None,
    target_name: str | None,
    context: dict[str, Any],
) -> str | None:
    if not case_run:
        return None
    deterministic_ref = case_run.get("deterministic_outcome_ref")
    if deterministic_ref and _is_absolute_uri(deterministic_ref):
        return deterministic_ref
    normalized = _normalize_label(target_name)
    if normalized:
        for fact in context["facts_by_name"].get(normalized, []):
            if fact.get("graph_uri") == case_run.get("graph_uri"):
                return fact.get("uri")
        matches = context["facts_by_name"].get(normalized, [])
        if matches:
            return matches[0].get("uri")
    return case_run.get("uri")


def _target_graph_uri(
    target_uri: str,
    case_run: dict[str, Any] | None,
    context: dict[str, Any],
) -> str:
    fact = context["facts_by_uri"].get(target_uri)
    if fact:
        return fact["graph_uri"]
    if case_run:
        return case_run["graph_uri"]
    return ""


def _traces_for_labels(
    labels: list[str | None],
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    traces: list[dict[str, Any]] = []
    for label in labels:
        normalized = _normalize_label(label)
        if not normalized:
            continue
        for trace in context["traces_by_name"].get(normalized, []):
            if trace["uri"] in seen:
                continue
            seen.add(trace["uri"])
            traces.append(trace)
    return traces


def _trace_labels(trace: dict[str, Any]) -> list[str]:
    return [
        value
        for value in (
            trace.get("question_name"),
            trace.get("node_name"),
            trace.get("fact_name"),
            trace.get("source_fact_name"),
        )
        if value
    ]


def _trace_display_label(trace: dict[str, Any]) -> str:
    return (
        trace.get("node_name")
        or trace.get("question_name")
        or trace.get("fact_name")
        or _short_uri(trace["uri"])
    )


def _index_by_normalized_name(
    index: dict[str, list[dict[str, Any]]],
    value: str | None,
    item: dict[str, Any],
) -> None:
    normalized = _normalize_label(value)
    if not normalized:
        return
    bucket = index.setdefault(normalized, [])
    if item not in bucket:
        bucket.append(item)


def _case_run_context_sparql(graphs: list[str]) -> str:
    return (
        "PREFIX inf: <http://inferra.ai/schema#>\n"
        "PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\n"
        "SELECT ?graph ?caseRun ?caseName ?ruleName ?targetNodeName "
        "?deterministicOutcomeRef ?deterministicOutcomeName ?deterministicOutcomeValue "
        "?fact ?factName ?factValue ?factSource ?factSession WHERE {\n"
        f"  VALUES ?graph {{ {_graph_values(graphs)} }}\n"
        "  GRAPH ?graph {\n"
        "    ?caseRun rdf:type inf:CaseRun .\n"
        "    OPTIONAL { ?caseRun inf:caseName ?caseName . }\n"
        "    OPTIONAL { ?caseRun inf:ruleName ?ruleName . }\n"
        "    OPTIONAL { ?caseRun inf:targetNodeName ?targetNodeName . }\n"
        "    OPTIONAL { ?caseRun inf:deterministicOutcomeRef ?deterministicOutcomeRef . }\n"
        "    OPTIONAL { ?caseRun inf:deterministicOutcomeName ?deterministicOutcomeName . }\n"
        "    OPTIONAL { ?caseRun inf:deterministicOutcomeValue ?deterministicOutcomeValue . }\n"
        "    OPTIONAL {\n"
        "      ?fact rdf:type inf:CaseFact ; inf:name ?factName ; inf:value ?factValue .\n"
        "      OPTIONAL { ?fact inf:factSource ?factSource . }\n"
        "      OPTIONAL { ?fact inf:session ?factSession . }\n"
        "    }\n"
        "  }\n"
        f"}} LIMIT {PATH_RESULT_LIMIT}"
    )


def _trace_context_sparql(graphs: list[str]) -> str:
    trace_values = " ".join(f"<{uri}>" for uri in TRACE_TYPE_URIS)
    return (
        "PREFIX inf: <http://inferra.ai/schema#>\n"
        "PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\n"
        "PREFIX prov: <http://www.w3.org/ns/prov#>\n"
        "SELECT ?graph ?trace ?traceType ?traceKind ?questionName ?nodeName "
        "?factName ?sourceFactName ?status ?action ?reason ?generatedBy WHERE {\n"
        f"  VALUES ?graph {{ {_graph_values(graphs)} }}\n"
        f"  VALUES ?traceType {{ {trace_values} }}\n"
        "  GRAPH ?graph {\n"
        "    ?trace rdf:type ?traceType .\n"
        "    OPTIONAL { ?trace inf:traceKind ?traceKind . }\n"
        "    OPTIONAL { ?trace inf:questionName ?questionName . }\n"
        "    OPTIONAL { ?trace inf:nodeName ?nodeName . }\n"
        "    OPTIONAL { ?trace inf:factName ?factName . }\n"
        "    OPTIONAL { ?trace inf:sourceFactName ?sourceFactName . }\n"
        "    OPTIONAL { ?trace inf:status ?status . }\n"
        "    OPTIONAL { ?trace inf:action ?action . }\n"
        "    OPTIONAL { ?trace inf:reason ?reason . }\n"
        "    OPTIONAL { ?trace prov:wasGeneratedBy ?generatedBy . }\n"
        "  }\n"
        f"}} LIMIT {PATH_RESULT_LIMIT}"
    )


def _projection_nodes_sparql(graphs: list[str]) -> str:
    return (
        "PREFIX inf: <http://inferra.ai/schema#>\n"
        "PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\n"
        "SELECT ?graph ?node ?name ?type WHERE {\n"
        f"  VALUES ?graph {{ {_graph_values(graphs)} }}\n"
        "  GRAPH ?graph {\n"
        "    ?node inf:name ?name .\n"
        "    OPTIONAL { ?node rdf:type ?type . }\n"
        "  }\n"
        f"}} LIMIT {PATH_RESULT_LIMIT}"
    )


def _projection_edges_sparql(graphs: list[str]) -> str:
    predicate_values = " ".join(f"<{uri}>" for uri in STRUCTURAL_PREDICATE_URIS)
    return (
        "SELECT ?graph ?source ?predicate ?target WHERE {\n"
        f"  VALUES ?graph {{ {_graph_values(graphs)} }}\n"
        f"  VALUES ?predicate {{ {predicate_values} }}\n"
        "  GRAPH ?graph { ?source ?predicate ?target . }\n"
        f"}} LIMIT {PATH_RESULT_LIMIT}"
    )


def _execute_path_select(sparql: str) -> list[dict[str, Any]]:
    return FusekiAdapter.execute_guarded_select(
        sparql,
        timeout_seconds=PATH_SELECT_TIMEOUT_SECONDS,
        max_retries=PATH_SELECT_MAX_RETRIES,
    )


def _graph_values(graphs: list[str]) -> str:
    return " ".join(f"<{graph_uri}>" for graph_uri in graphs)


def _binding_value(binding: dict[str, Any], name: str) -> str | None:
    value = binding.get(name)
    if isinstance(value, dict) and "value" in value:
        return str(value["value"])
    if value is None:
        return None
    return str(value)


def _normalize_label(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value.strip().lower())


def _is_absolute_uri(value: str | None) -> bool:
    return bool(value and str(value).strip().startswith(("http://", "https://", "urn:")))


def _predicate_label(uri: str) -> str:
    return re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", _short_uri(uri)).replace("_", " ")


def _short_uri(uri: str) -> str:
    return uri[max(uri.rfind("#"), uri.rfind("/"), uri.rfind(":")) + 1 :]


def _unique_stable(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _list_available_graphs() -> dict[str, int]:
    try:
        return {
            uri: triple_count
            for uri, triple_count in FusekiAdapter.list_named_graphs()
        }
    except FusekiConnectionError as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": "fuseki_graph_inventory_unavailable", "message": str(exc)},
        ) from exc


def _validate_selected_graphs(
    selected_graph_uris: list[str],
    available_graphs: dict[str, int],
) -> list[str]:
    selected_graphs: list[str] = []
    for graph_uri in selected_graph_uris:
        _validate_chat_graph_uri(graph_uri)
        if graph_uri not in available_graphs:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "selected_graph_not_available",
                    "message": f"Selected graph is not available in Fuseki: {graph_uri}",
                    "available_graph_count": len(available_graphs),
                },
            )
        resolved_graph_uri = _resolve_latest_full_semantic_pointer(graph_uri)
        _validate_chat_graph_uri(resolved_graph_uri)
        selected_graphs.append(resolved_graph_uri)
    return selected_graphs


def _resolve_chat_sparql(
    request: OntologyChatQueryRequest,
    selected_graphs: list[str],
    *,
    candidate: OntologyChatQueryCandidate | None = None,
) -> tuple[str, str, str, str | None]:
    if candidate is None:
        return (
            _default_chat_sparql(selected_graphs, request.row_limit),
            "deterministic_template",
            "deterministic-template-v1",
            "Default bounded scan over the selected named graphs.",
        )

    if not candidate.sparql:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "candidate_missing_sparql",
                "message": "Structured query candidates must include sparql when status=query.",
            },
        )
    return (
        candidate.sparql.strip(),
        "structured_candidate",
        candidate.contract_version,
        candidate.rationale,
    )


def _default_chat_sparql(selected_graphs: list[str], row_limit: int) -> str:
    graph_values = " ".join(f"<{graph_uri}>" for graph_uri in selected_graphs)
    return (
        "SELECT ?graph ?subject ?predicate ?object WHERE {\n"
        f"  VALUES ?graph {{ {graph_values} }}\n"
        "  GRAPH ?graph { ?subject ?predicate ?object . }\n"
        f"}} LIMIT {row_limit}"
    )


def _guardrail_receipt(
    *,
    selected_graphs: list[str],
    available_graph_count: int,
    query_length: int,
    row_limit: int,
    timeout_seconds: int,
    max_retries: int,
    read_only: bool = False,
    graph_scope_validated: bool = False,
    blocked_operations: list[str] | None = None,
    checks: dict[str, bool] | None = None,
) -> OntologyChatGuardrailReceipt:
    return OntologyChatGuardrailReceipt(
        read_only=read_only,
        graph_scope_validated=graph_scope_validated,
        selected_graph_count=len(selected_graphs),
        available_graph_count=available_graph_count,
        query_length=query_length,
        max_query_length=MAX_CHAT_QUERY_LENGTH,
        row_limit=row_limit,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        blocked_operations=blocked_operations or [],
        checks=checks or {},
    )


def _validate_guarded_sparql(
    sparql: str,
    *,
    selected_graphs: list[str],
    row_limit: int,
    receipt: OntologyChatGuardrailReceipt,
) -> None:
    if len(sparql) > MAX_CHAT_QUERY_LENGTH:
        _block_query(
            "query_too_long",
            "SPARQL query exceeds the maximum query length.",
            receipt,
        )

    operation = _query_operation(sparql)
    if operation != "SELECT":
        _block_query(
            "query_must_be_select",
            "Ontology chat only permits read-only SELECT queries.",
            receipt,
            blocked_operations=[operation] if operation else [],
        )

    tokens = _sparql_tokens(sparql)
    blocked_tokens = sorted(tokens.intersection(UNSAFE_SPARQL_TOKENS))
    if "FROM" in tokens:
        blocked_tokens.append("FROM")
    if blocked_tokens:
        _block_query(
            "unsafe_sparql_operation",
            "SPARQL query contains an unsafe operation.",
            receipt,
            blocked_operations=sorted(set(blocked_tokens)),
        )

    _validate_sparql_parse(sparql, receipt)
    _validate_no_default_graph_patterns(sparql, receipt)
    _validate_graph_scope(sparql, selected_graphs, receipt)
    _validate_limit(sparql, row_limit, receipt)


def _query_operation(sparql: str) -> str | None:
    query = _strip_sparql_comments(sparql).lstrip()
    directive = re.compile(
        r"^(?:PREFIX\s+[\w-]*:\s*<[^>]*>|BASE\s*<[^>]*>)\s*",
        re.IGNORECASE,
    )
    while True:
        match = directive.match(query)
        if match is None:
            break
        query = query[match.end() :].lstrip()
    match = re.match(r"([A-Za-z]+)\b", query)
    return match.group(1).upper() if match else None


def _sparql_tokens(sparql: str) -> set[str]:
    scrubbed = _strip_sparql_literals_comments_and_iris(sparql)
    return {token.upper() for token in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", scrubbed)}


def _validate_sparql_parse(
    sparql: str,
    receipt: OntologyChatGuardrailReceipt,
) -> None:
    try:
        from rdflib.plugins.sparql.parser import parseQuery
    except ModuleNotFoundError:
        if sparql.count("{") != sparql.count("}") or "{" not in sparql:
            _block_query(
                "invalid_sparql",
                "SPARQL query failed basic syntax validation.",
                receipt,
            )
        if "WHERE" not in _sparql_tokens(sparql):
            _block_query(
                "invalid_sparql",
                "SPARQL query must include an explicit WHERE clause.",
                receipt,
            )
        return

    try:
        parseQuery(sparql)
    except Exception as exc:
        _block_query(
            "invalid_sparql",
            f"SPARQL parser rejected the query: {exc}",
            receipt,
        )


def _validate_no_default_graph_patterns(
    sparql: str,
    receipt: OntologyChatGuardrailReceipt,
) -> None:
    try:
        from pyparsing import ParseResults
        from rdflib.plugins.sparql.parser import parseQuery
        from rdflib.plugins.sparql.parserutils import CompValue
    except ModuleNotFoundError:
        _block_query(
            "sparql_parser_unavailable",
            "SPARQL parser is required for complete graph-scope validation.",
            receipt,
        )

    try:
        parsed = parseQuery(sparql)
    except Exception as exc:
        _block_query(
            "invalid_sparql",
            f"SPARQL parser rejected the query: {exc}",
            receipt,
        )

    if _contains_default_graph_triples(
        parsed,
        in_named_graph=False,
        parse_results_type=ParseResults,
        comp_value_type=CompValue,
    ):
        _block_query(
            "unscoped_default_graph_access",
            "SPARQL query must place every triple pattern inside a selected GRAPH block.",
            receipt,
        )


def _contains_default_graph_triples(
    value: Any,
    *,
    in_named_graph: bool,
    parse_results_type: type,
    comp_value_type: type,
) -> bool:
    if isinstance(value, comp_value_type):
        name = getattr(value, "name", None)
        if name == "GraphGraphPattern":
            return _contains_default_graph_triples(
                value.get("graph"),
                in_named_graph=True,
                parse_results_type=parse_results_type,
                comp_value_type=comp_value_type,
            )
        if name == "TriplesBlock":
            return bool(value.get("triples")) and not in_named_graph
        return any(
            _contains_default_graph_triples(
                child,
                in_named_graph=in_named_graph,
                parse_results_type=parse_results_type,
                comp_value_type=comp_value_type,
            )
            for child in value.values()
        )

    if isinstance(value, (list, tuple, parse_results_type)):
        return any(
            _contains_default_graph_triples(
                child,
                in_named_graph=in_named_graph,
                parse_results_type=parse_results_type,
                comp_value_type=comp_value_type,
            )
            for child in value
        )

    return False


def _validate_graph_scope(
    sparql: str,
    selected_graphs: list[str],
    receipt: OntologyChatGuardrailReceipt,
) -> None:
    graph_scope_uris, unbound_vars = _extract_graph_scope_uris(sparql)
    if unbound_vars:
        _block_query(
            "unbound_graph_scope",
            "GRAPH variables must be constrained by VALUES to selected graph URIs.",
            receipt,
        )
    if not graph_scope_uris:
        _block_query(
            "unscoped_graph_query",
            "SPARQL query must explicitly scope results to selected named graphs.",
            receipt,
        )

    selected = set(selected_graphs)
    out_of_scope = sorted(uri for uri in graph_scope_uris if uri not in selected)
    if out_of_scope:
        _block_query(
            "out_of_scope_graph",
            "SPARQL query references graph URIs outside the selected scope.",
            receipt,
            blocked_operations=out_of_scope,
        )


def _extract_graph_scope_uris(sparql: str) -> tuple[set[str], set[str]]:
    refs = set(re.findall(r"(?<![?\w])GRAPH\s*<([^>]+)>", sparql, flags=re.IGNORECASE))
    graph_vars = {
        match.group(1)
        for match in re.finditer(
            r"(?<![?\w])GRAPH\s+(\?[A-Za-z_][\w-]*)\b",
            sparql,
            flags=re.IGNORECASE,
        )
    }
    unbound_vars: set[str] = set()
    for graph_var in graph_vars:
        values_pattern = re.compile(
            rf"\bVALUES\s+{re.escape(graph_var)}\s*\{{(?P<body>[^}}]+)\}}",
            re.IGNORECASE | re.DOTALL,
        )
        matches = list(values_pattern.finditer(sparql))
        if not matches:
            unbound_vars.add(graph_var)
            continue
        for match in matches:
            refs.update(re.findall(r"<([^>]+)>", match.group("body")))
    return refs, unbound_vars


def _validate_limit(
    sparql: str,
    row_limit: int,
    receipt: OntologyChatGuardrailReceipt,
) -> None:
    scrubbed = _strip_sparql_literals_comments_and_iris(sparql)
    limits = [
        int(value)
        for value in re.findall(r"\bLIMIT\s+(\d+)\b", scrubbed, flags=re.IGNORECASE)
    ]
    if not limits:
        _block_query(
            "unbounded_query",
            "SPARQL query must include a LIMIT bounded by row_limit.",
            receipt,
        )
    if any(value > row_limit for value in limits):
        _block_query(
            "over_limit_query",
            "SPARQL LIMIT exceeds the requested row_limit cap.",
            receipt,
        )


def _block_query(
    error: str,
    message: str,
    receipt: OntologyChatGuardrailReceipt,
    *,
    blocked_operations: list[str] | None = None,
) -> None:
    if blocked_operations:
        receipt.blocked_operations = blocked_operations
    raise HTTPException(
        status_code=400,
        detail={
            "error": error,
            "message": message,
            "guardrail_receipt": receipt.model_dump(),
        },
    )


def _rows_from_bindings(
    bindings: list[dict[str, Any]],
) -> list[dict[str, OntologyChatBindingValue]]:
    rows: list[dict[str, OntologyChatBindingValue]] = []
    for binding in bindings:
        row: dict[str, OntologyChatBindingValue] = {}
        for variable, value in binding.items():
            if isinstance(value, dict) and "value" in value:
                row[variable] = OntologyChatBindingValue.model_validate(value)
            else:
                row[variable] = OntologyChatBindingValue(value=str(value))
        rows.append(row)
    return rows


def _overlay_targets(
    rows: list[dict[str, OntologyChatBindingValue]],
    selected_graphs: list[str],
) -> dict[str, OntologyChatGraphOverlayTargets]:
    overlays = {
        graph_uri: OntologyChatGraphOverlayTargets()
        for graph_uri in selected_graphs
    }
    for row_index, row in enumerate(rows):
        graph_uri = _uri_value(row, "graph", "g")
        if graph_uri is None and len(selected_graphs) == 1:
            graph_uri = selected_graphs[0]
        if graph_uri not in overlays:
            continue

        subject_uri = _uri_value(
            row,
            "subject",
            "s",
            "node",
            "fact",
            "caseFact",
            "caseRun",
            "trace",
            "strategy",
            "selected",
            "selectedUri",
        )
        predicate_uri = _uri_value(row, "predicate", "p")
        object_uri = _uri_value(row, "object", "o", "target")
        if subject_uri is not None:
            _append_node_overlay(overlays[graph_uri], subject_uri, row_index)
        if object_uri is not None:
            _append_node_overlay(overlays[graph_uri], object_uri, row_index)
        if subject_uri and predicate_uri and object_uri:
            _append_edge_overlay(
                overlays[graph_uri],
                subject_uri,
                predicate_uri,
                object_uri,
                row_index,
            )
    return overlays


def _append_node_overlay(
    overlay: OntologyChatGraphOverlayTargets,
    uri: str,
    row_index: int,
) -> None:
    target = overlay.nodes.setdefault(uri, OntologyChatOverlayNodeTarget())
    if row_index not in target.row_indices:
        target.row_indices.append(row_index)


def _append_edge_overlay(
    overlay: OntologyChatGraphOverlayTargets,
    source_uri: str,
    predicate_uri: str,
    target_uri: str,
    row_index: int,
) -> None:
    key = f"{source_uri}|{predicate_uri}|{target_uri}"
    target = overlay.edges.setdefault(
        key,
        OntologyChatOverlayEdgeTarget(
            source_uri=source_uri,
            predicate_uri=predicate_uri,
            target_uri=target_uri,
        ),
    )
    if row_index not in target.row_indices:
        target.row_indices.append(row_index)


def _uri_value(row: dict[str, OntologyChatBindingValue], *names: str) -> str | None:
    for name in names:
        value = row.get(name)
        if value and value.type == "uri":
            return value.value
    return None


def _chat_provenance(
    query_source: str,
    *,
    executed: bool,
    candidate_provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    provenance = {
        "graph_inventory": "fuseki_named_graphs",
        "query_source": query_source,
        "execution_backend": "fuseki" if executed else None,
        "advisory_invariant": "ontology_analysis_does_not_mutate_rule_outcomes",
    }
    if candidate_provenance:
        provenance["candidate"] = candidate_provenance
    return provenance


def _validate_chat_graph_uri(uri: str) -> None:
    value = str(uri).strip()
    if not value.startswith(("http://", "https://", "urn:")):
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_graph_uri", "message": "Graph URI must be absolute."},
        )
    if any(char in value for char in "<>\"{}|^`\\"):
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_graph_uri", "message": "Graph URI contains invalid characters."},
        )


def _strip_sparql_comments(sparql: str) -> str:
    result: list[str] = []
    in_iri = False
    quote: str | None = None
    escaped = False
    index = 0
    while index < len(sparql):
        char = sparql[index]
        if quote is not None:
            result.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue

        if in_iri:
            result.append(char)
            if char == ">":
                in_iri = False
            index += 1
            continue

        if char in {"'", '"'}:
            quote = char
            result.append(char)
            index += 1
            continue
        if char == "<":
            in_iri = True
            result.append(char)
            index += 1
            continue
        if char == "#":
            while index < len(sparql) and sparql[index] not in "\r\n":
                index += 1
            result.append(" ")
            continue
        result.append(char)
        index += 1
    return "".join(result)


def _strip_sparql_literals_comments_and_iris(sparql: str) -> str:
    scrubbed = _strip_sparql_comments(sparql)
    replacements = [
        r'""".*?"""',
        r"'''.*?'''",
        r'"(?:\\.|[^"\\])*"',
        r"'(?:\\.|[^'\\])*'",
        r"<[^>]*>",
    ]
    for pattern in replacements:
        scrubbed = re.sub(pattern, " ", scrubbed, flags=re.DOTALL)
    return scrubbed

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FusekiNamedGraphResponse(BaseModel):
    uri: str
    triple_count: int


class FusekiGraphListResponse(BaseModel):
    graphs: list[FusekiNamedGraphResponse]
    total_count: int


class FusekiTripleResponse(BaseModel):
    subject: str
    predicate: str
    object: str


class FusekiGraphNodeResponse(BaseModel):
    uri: str
    name: str | None = None
    types: list[str] = Field(default_factory=list)


class FusekiGraphEdgeResponse(BaseModel):
    subject: str
    predicate: str
    object: str


class FusekiGraphResponse(BaseModel):
    graph_uri: str
    triple_count: int
    triples: list[FusekiTripleResponse]
    nodes: list[FusekiGraphNodeResponse]
    edges: list[FusekiGraphEdgeResponse]
    offset: int
    limit: int


class OntologyChatQueryCandidate(BaseModel):
    contract_version: Literal["ontology-chat-query-v1"] = "ontology-chat-query-v1"
    status: Literal["query", "abstain"] = "query"
    sparql: str | None = Field(default=None, max_length=6000)
    rationale: str | None = Field(default=None, max_length=1000)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    provenance: dict[str, Any] = Field(default_factory=dict)


class OntologyChatQueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    selected_graph_uris: list[str] = Field(..., min_length=1, max_length=10)
    candidate: OntologyChatQueryCandidate | None = None
    row_limit: int = Field(default=100, ge=1, le=500)
    timeout_seconds: int = Field(default=10, ge=1, le=10)
    max_retries: int = Field(default=0, ge=0, le=1)

    @field_validator("selected_graph_uris")
    @classmethod
    def selected_graphs_must_be_unique(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value]
        if any(not item for item in normalized):
            raise ValueError("selected_graph_uris cannot contain empty values")
        if len(set(normalized)) != len(normalized):
            raise ValueError("selected_graph_uris must be unique")
        return normalized


class OntologyChatBindingValue(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: str | None = None
    value: str
    datatype: str | None = None
    lang: str | None = Field(default=None, alias="xml:lang")


class OntologyChatOverlayNodeTarget(BaseModel):
    row_indices: list[int] = Field(default_factory=list)


class OntologyChatOverlayEdgeTarget(BaseModel):
    source_uri: str
    predicate_uri: str
    target_uri: str
    row_indices: list[int] = Field(default_factory=list)


class OntologyChatGraphOverlayTargets(BaseModel):
    nodes: dict[str, OntologyChatOverlayNodeTarget] = Field(default_factory=dict)
    edges: dict[str, OntologyChatOverlayEdgeTarget] = Field(default_factory=dict)


class OntologyChatQueryDetails(BaseModel):
    source: Literal["deterministic_template", "structured_candidate", "abstained"]
    contract_version: str
    sparql: str | None = None
    rationale: str | None = None
    validation_status: Literal["validated", "abstained"]
    selected_graph_uris: list[str]
    result_limit: int
    timeout_seconds: int


class OntologyChatGuardrailReceipt(BaseModel):
    read_only: bool
    graph_scope_validated: bool
    selected_graph_count: int
    available_graph_count: int
    query_length: int
    max_query_length: int
    row_limit: int
    timeout_seconds: int
    max_retries: int
    result_cap_applied: bool = False
    deterministic_rule_outcomes_mutated: bool = False
    blocked_operations: list[str] = Field(default_factory=list)
    checks: dict[str, bool] = Field(default_factory=dict)


class OntologyChatQueryResponse(BaseModel):
    status: Literal["ok", "abstained"]
    question: str
    advisory_only: bool = True
    advisory_status: Literal["advisory_evidence_only"] = "advisory_evidence_only"
    query_details: OntologyChatQueryDetails
    rows: list[dict[str, OntologyChatBindingValue]]
    overlay_targets: dict[str, OntologyChatGraphOverlayTargets]
    guardrail_receipt: OntologyChatGuardrailReceipt
    provenance: dict[str, Any] = Field(default_factory=dict)


class OntologyPathResolveRequest(BaseModel):
    selected_graph_uris: list[str] = Field(..., min_length=1, max_length=10)
    active_graph_uri: str | None = None
    selected_row_index: int | None = Field(default=None, ge=0)
    selected_row: dict[str, OntologyChatBindingValue] | None = None
    selected_uri: str | None = None
    selected_label: str | None = Field(default=None, max_length=1000)
    direction: Literal[
        "both",
        "evidence_to_conclusion",
        "conclusion_to_evidence",
    ] = "both"
    max_depth: int = Field(default=8, ge=1, le=20)

    @field_validator("selected_graph_uris")
    @classmethod
    def selected_graphs_must_be_unique(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value]
        if any(not item for item in normalized):
            raise ValueError("selected_graph_uris cannot contain empty values")
        if len(set(normalized)) != len(normalized):
            raise ValueError("selected_graph_uris must be unique")
        return normalized


class OntologyDecisionPathNode(BaseModel):
    uri: str
    label: str
    graph_uri: str
    role: Literal[
        "selected",
        "conclusion",
        "fact",
        "trace",
        "case_run",
        "projection_node",
        "unknown",
    ]
    match_kind: Literal[
        "exact_uri",
        "target_conclusion",
        "exact_normalized_label",
        "trace_normalized_label",
        "projection_normalized_label",
        "structural_reference",
        "related",
        "unknown",
    ] = "unknown"


class OntologyDecisionPathEdge(BaseModel):
    source_uri: str
    predicate_uri: str
    target_uri: str
    label: str
    graph_uri: str
    relationship_type: Literal[
        "authoritative_case_fact",
        "authoritative_outcome",
        "semantic_trace",
        "projection_dependency",
        "projection_structure",
        "soft_match",
        "unknown",
    ]
    direction: Literal[
        "evidence_to_conclusion",
        "conclusion_to_evidence",
        "bidirectional",
        "stored",
    ] = "stored"


class OntologyPathResolveResponse(BaseModel):
    status: Literal["ok", "no_path"]
    selected_uri: str | None = None
    selected_label: str | None = None
    target_uri: str | None = None
    target_node_name: str | None = None
    authoritative_graph_uris: list[str] = Field(default_factory=list)
    structural_graph_uris: list[str] = Field(default_factory=list)
    nodes: list[OntologyDecisionPathNode] = Field(default_factory=list)
    edges: list[OntologyDecisionPathEdge] = Field(default_factory=list)
    relationship_summary: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)

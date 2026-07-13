from typing import Any, Optional

from pydantic import BaseModel, Field

from src.adapters.inbound.http.schemas.ontology_artifacts import (
    OntologyArtifactMetadataResponse,
)


class RuleSummaryResponse(BaseModel):
    rule_id: int | None = None
    name: str | None = None
    category: str | None = None
    description: str | None = None


class RuleTextResponse(BaseModel):
    ruleText: str


class RuleTreeDataResponse(BaseModel):
    ruleTreeData: str


class RuleGraphNodeResponse(BaseModel):
    name: str
    stable_id: str | None = None
    runtime_id: int | None = None
    module: str | None = None
    import_namespace: str | None = None
    import_version: str | None = None
    imported: bool | None = None
    import_depth: int | None = None


class RuleGraphEdgeResponse(BaseModel):
    parent: str
    child: str
    dep_type: int | str


class RuleGraphResponse(BaseModel):
    rule_name: str
    source: str
    rule_text: str
    expanded_rule_text: str
    schema_version: int
    nodes: list[RuleGraphNodeResponse]
    edges: list[RuleGraphEdgeResponse]


class RuleOntologyTripleResponse(BaseModel):
    subject: str
    predicate: str
    object: str


class RuleOntologyNodeResponse(BaseModel):
    uri: str
    name: str | None = None
    types: list[str] = Field(default_factory=list)
    type_key: str | None = None
    in_degree: int = 0
    out_degree: int = 0
    degree: int = 0
    layout_weight: float = 0.0


class RuleOntologyEdgeResponse(BaseModel):
    subject: str
    predicate: str
    object: str
    predicate_key: str | None = None
    dependency_type: str | None = None


class RuleOntologyResponse(BaseModel):
    rule_name: str
    source: str
    triple_count: int
    source_hash: str | None = None
    compiler_version: str | None = None
    compiled_triple_count: int = 0
    stored_triple_count: int = 0
    graph_uri: str | None = None
    sync_status: str = "unknown"
    sync_timestamp: str | None = None
    dead_letter_visible: bool = False
    dead_letter_id: str | None = None
    last_error_code: str | None = None
    last_error_summary: str | None = None
    job_id: str | None = None
    integrity_status: str = "unknown"
    integrity_mismatch_reason: str | None = None
    artifact: OntologyArtifactMetadataResponse | None = None
    triples: list[RuleOntologyTripleResponse]
    nodes: list[RuleOntologyNodeResponse]
    edges: list[RuleOntologyEdgeResponse]


class RuleOntologySyncResponse(BaseModel):
    rule_name: str
    status: str
    sync_status: str = "unknown"
    task_id: str | None = None
    triple_count: int = 0
    source_hash: str | None = None
    compiler_version: str | None = None
    compiled_triple_count: int = 0
    stored_triple_count: int | None = None
    graph_uri: str | None = None
    last_error_code: str | None = None
    last_error_summary: str | None = None


class RuleOntologyBatchSyncResponse(BaseModel):
    status: str
    requested_count: int
    published_count: int
    skipped_count: int
    failed_count: int = 0
    items: list[RuleOntologySyncResponse] = Field(default_factory=list)


class UpdateRuleRequest(BaseModel):
    oldRuleName: str
    newRuleName: str
    newRuleCategory: str


class UpdateRuleResponse(BaseModel):
    newRuleName: str | None = None
    newCategory: str | None = None


class CreateRuleRequest(BaseModel):
    name: str
    category: str
    description: str


class SaveConvertedRuleRequest(CreateRuleRequest):
    ruleText: str
    waived_error_ids: Optional[list[str]] = None


class RuleCreatedResponse(BaseModel):
    ruleName: str | None = None
    category: str | None = None
    description: str | None = None


class CreateRuleFileRequest(BaseModel):
    ruleName: str
    ruleText: str
    waived_error_ids: Optional[list[str]] = None


class LatestRuleFileResponse(BaseModel):
    fileId: int | None = None
    ruleId: int | None = None
    ruleText: str


class LatestRuleHistoryResponse(BaseModel):
    ruleId: int | None = None
    ruleName: str | None = None
    history: dict[str, Any]


class RuleSetCreateRequest(BaseModel):
    rule_name: str = Field(..., min_length=1, max_length=255)
    category: str = Field("", max_length=255)
    description: str = Field("", max_length=2000)
    rule_text: str = Field(..., min_length=1, max_length=1_000_000)
    waived_error_ids: Optional[list[str]] = None


class RuleSetVersionCreateRequest(BaseModel):
    rule_text: str = Field(..., min_length=1, max_length=1_000_000)
    waived_error_ids: Optional[list[str]] = None


class RuleSetSummaryResponse(BaseModel):
    rule_id: int | None = None
    rule_name: str
    category: str | None = None
    description: str | None = None


class RuleSetDetailResponse(RuleSetSummaryResponse):
    rule_text: str
    latest_file_id: int | None = None


class RuleSetVersionResponse(BaseModel):
    rule_name: str
    rule_text: str
    latest_file_id: int | None = None

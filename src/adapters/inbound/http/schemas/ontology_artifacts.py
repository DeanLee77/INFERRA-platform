from pydantic import BaseModel, Field


class CaseRunSyncRequest(BaseModel):
    case_run_name: str = Field(..., min_length=1, description="Human-readable name for this case run")
    ontology_profile: str | None = Field(
        None,
        description=(
            "Optional ontology profile for the artifact being synced. "
            "Use full_semantic_pilot to store under the full-semantic graph namespace."
        ),
    )
    versioned: bool = Field(
        True,
        description="Store full_semantic_pilot artifacts under an immutable version URI and update /latest pointer",
    )
    original_decision_name: str | None = Field(
        None,
        description="Locked decision node name from the original case execution, when syncing a full semantic run",
    )
    original_decision_value: str | None = Field(
        None,
        description="Locked decision value from the original case execution, when syncing a full semantic run",
    )


class CaseRunSyncResponse(BaseModel):
    status: str
    graph_uri: str
    triple_count: int
    session_id: str
    case_run_name: str
    latest_graph_uri: str | None = None
    version_graph_uri: str | None = None
    semantic_completion_status: str | None = None


class CaseRunCollisionCheckResponse(BaseModel):
    exists: bool
    triple_count: int
    graph_uri: str
    latest_graph_uri: str | None = None
    version_graph_uri: str | None = None


class OntologyArtifactMetadataResponse(BaseModel):
    artifact_name: str
    artifact_kind: str
    media_type: str = "text/turtle"
    rule_name: str
    graph_uri: str
    projection_graph_uri: str | None = None
    source_hash: str
    compiler_version: str
    triple_count: int
    artifact_uri: str | None = None
    download_url: str | None = None
    session_id: str | None = None
    case_name: str | None = None
    target_node_name: str | None = None
    deterministic_outcome_ref: str | None = None
    semantic_completion_status: str | None = None
    latest_graph_uri: str | None = None
    version_graph_uri: str | None = None


class OntologyArtifactResponse(OntologyArtifactMetadataResponse):
    turtle: str = Field(..., description="Serialized ontology artifact in Turtle format")

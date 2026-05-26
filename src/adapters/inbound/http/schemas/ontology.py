from pydantic import BaseModel, Field


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

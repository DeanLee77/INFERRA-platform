"""
Prometheus Metrics Router.

Exposes `/metrics` endpoint in Prometheus text exposition format for
async pipeline observability. Metrics cover Fuseki sync, graph
propagation, import resolution, and semantic cache state.
"""

from fastapi import APIRouter
from prometheus_client import Counter, Gauge, Histogram, generate_latest
from starlette.responses import PlainTextResponse

router = APIRouter(tags=["metrics"])

PROMETHEUS_AVAILABLE = True

fuseki_sync_total = Counter(
    "inferra_fuseki_sync_total",
    "Fuseki sync operations",
    ["status"],
)

propagation_total = Counter(
    "inferra_propagation_total",
    "Graph propagation operations",
    ["direction"],
)

import_resolve_total = Counter(
    "inferra_import_resolve_total",
    "Import resolution operations",
    ["result"],
)

fuseki_sync_duration = Histogram(
    "inferra_fuseki_sync_duration_seconds",
    "Fuseki sync latency",
)

propagation_duration = Histogram(
    "inferra_propagation_duration_seconds",
    "Propagation latency",
    ["direction"],
)

import_resolve_depth = Histogram(
    "inferra_import_resolve_depth",
    "Import DFS depth",
)

semantic_cache_triples = Gauge(
    "inferra_semantic_cache_triples_loaded",
    "Triple count in semantic cache",
)

semantic_cache_memory_mb = Gauge(
    "inferra_semantic_cache_memory_mb",
    "Semantic cache memory usage MB",
)

semantic_cache_hit_rate = Gauge(
    "inferra_semantic_cache_hit_rate",
    "Semantic cache hit rate",
)

abduction_total = Counter(
    "inferra_abduction_total",
    "Abduction endpoint outcomes",
    ["status"],
)

abduction_hypothesis_count = Histogram(
    "inferra_abduction_hypothesis_count",
    "Number of hypotheses returned by abduction",
    buckets=[0, 1, 2, 3, 5, 10, 25, 50],
)

induction_total = Counter(
    "inferra_induction_total",
    "Induction endpoint outcomes",
    ["operation", "status"],
)

reasoning_route_total = Counter(
    "inferra_reasoning_route_total",
    "Reasoning API route outcomes",
    ["mode", "action"],
)

llm_call_total = Counter(
    "inferra_llm_call_total",
    "LLM orchestration outcomes",
    ["operation", "status"],
)

llm_confidence_score = Histogram(
    "inferra_llm_confidence_score",
    "LLM goal-mapping confidence scores",
    buckets=[0.0, 0.25, 0.5, 0.65, 0.8, 0.9, 1.0],
)

llm_response_length = Histogram(
    "inferra_llm_response_length_chars",
    "LLM response length in characters",
    buckets=[0, 50, 100, 250, 500, 1000, 2500, 6000],
)


def _refresh_semantic_cache_gauges() -> None:
    try:
        from src.adapters.outbound.ontology.semantic_cache import get_semantic_cache

        cache = get_semantic_cache()
        semantic_cache_triples.set(cache.triple_count)
        semantic_cache_memory_mb.set(cache.memory_usage_mb)
        semantic_cache_hit_rate.set(cache.hit_rate)
    except Exception:
        semantic_cache_triples.set(0)
        semantic_cache_memory_mb.set(0.0)
        semantic_cache_hit_rate.set(0.0)


@router.get("/metrics")
async def metrics() -> PlainTextResponse:
    _refresh_semantic_cache_gauges()
    return PlainTextResponse(generate_latest(), media_type="text/plain; version=0.0.4; charset=utf-8")


@router.get("/api/v1/metrics")
async def metrics_v1() -> PlainTextResponse:
    return await metrics()

from typing import Optional
from urllib.parse import quote

import structlog

from src.domain.session.inference_context import InferenceContext

log = structlog.get_logger(__name__)


class ProvOTraceGenerator:
    """Generate PROV-O compatible traces from an InferenceContext."""

    INFERRA_NS = "https://inferra.local/ns#"
    PROV_NS = "http://www.w3.org/ns/prov#"

    def generate(self, ctx: InferenceContext, output_format: str = "turtle") -> str:
        try:
            from rdflib import Graph, Literal, Namespace, RDF, URIRef
        except ImportError as exc:
            raise RuntimeError("rdflib is required for PROV-O trace generation") from exc

        graph = Graph()
        inf = Namespace(self.INFERRA_NS)
        prov = Namespace(self.PROV_NS)
        graph.bind("inf", inf)
        graph.bind("prov", prov)

        session_uri = URIRef(inf[f"session/{self._safe(ctx.session_id)}"])
        graph.add((session_uri, RDF.type, inf.Session))
        graph.add((session_uri, inf.ruleName, Literal(ctx.rule_name)))
        graph.add((session_uri, inf.target, Literal(ctx.target)))
        graph.add((session_uri, inf.iterationCount, Literal(ctx.iteration_count)))

        fact_store = ctx.fact_store
        working_memory = fact_store.get_unified_view()
        for name, fact in sorted(working_memory.items()):
            fact_uri = URIRef(inf[f"fact/{self._safe(ctx.session_id)}/{self._safe(name)}"])
            graph.add((fact_uri, RDF.type, inf.Conclusion))
            graph.add((fact_uri, inf.name, Literal(name)))
            graph.add((fact_uri, inf.value, Literal(str(fact.get_value()))))
            graph.add((fact_uri, prov.wasGeneratedBy, session_uri))
            sources = sorted(source.value for source in fact_store.get_fact_sources(name))
            for source in sources:
                graph.add((fact_uri, inf.factSource, Literal(source)))

        fmt = "json-ld" if output_format in {"json-ld", "jsonld"} else "turtle"
        result = graph.serialize(format=fmt)
        log.info(
            "prov_o_trace_generated",
            session_id=ctx.session_id,
            triple_count=len(graph),
            output_format=fmt,
        )
        return result.decode("utf-8") if isinstance(result, bytes) else str(result)

    def _safe(self, value: Optional[str]) -> str:
        return quote(value or "unknown", safe="")

"""Ontology outbound adapters — RDF compilation, Fuseki, and semantic cache."""

from src.adapters.outbound.ontology import fuseki_adapter, inferra_to_rdf_compiler

__all__ = ["fuseki_adapter", "inferra_to_rdf_compiler"]

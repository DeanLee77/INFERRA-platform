"""
InferraToRdfCompiler — compiles INFERRA rule text to RDF triples.

Translates rule structures (AND/OR dependencies, iterate blocks,
value conclusions) into an OWL-Mini-compatible RDF graph using
the inf: namespace. The compiled triples are pushed to Fuseki
via idempotent SPARQL DELETE/INSERT patterns.

RDF Namespace:
    inf: <http://inferra.ai/schema#>
    rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    rdfs: <http://www.w3.org/2000/01/rdf-schema#>
"""

import re
from typing import List, Tuple

import structlog

log = structlog.get_logger()

INF_NS = "http://inferra.ai/schema#"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"

RULE_TYPES = {
    "AND": f"{INF_NS}AndRule",
    "OR": f"{INF_NS}OrRule",
    "ITERATE": f"{INF_NS}IterateRule",
    "CONCLUSION": f"{INF_NS}Conclusion",
}

DEPENDENCY_PREDICATES = {
    "AND": f"{INF_NS}andDependsOn",
    "OR": f"{INF_NS}orDependsOn",
}


class InferraToRdfCompiler:
    """Compiles INFERRA rule text to RDF triples for Fuseki projection."""

    @staticmethod
    def compile(rule_text: str, rule_name: str) -> List[Tuple[str, str, str]]:
        """
        Compile rule text into a list of RDF triples.

        Each triple is (subject, predicate, object). The rule_name is used
        as the subject URI base.

        Args:
            rule_text: Full text content of the rule
            rule_name: Name of the rule (used as URI base)

        Returns:
            List of (subject, predicate, object) tuples
        """
        triples: List[Tuple[str, str, str]] = []
        rule_uri = f"{INF_NS}rule/{_sanitize_uri(rule_name)}"

        triples.append((rule_uri, RDF_TYPE, f"{INF_NS}Rule"))
        triples.append((rule_uri, f"{INF_NS}name", rule_name))
        triples.append((rule_uri, f"{INF_NS}sourceText", rule_text))

        rule_type = _infer_rule_type(rule_text)
        if rule_type:
            triples.append((rule_uri, RDF_TYPE, RULE_TYPES[rule_type]))

            predicate = DEPENDENCY_PREDICATES.get(rule_type)
            if predicate:
                children = _extract_children(rule_text)
                for child in children:
                    child_uri = f"{INF_NS}node/{_sanitize_uri(child)}"
                    triples.append((rule_uri, predicate, child_uri))
                    triples.append((child_uri, RDF_TYPE, f"{INF_NS}Node"))
                    triples.append((child_uri, f"{INF_NS}name", child))

        quantifier = _extract_quantifier(rule_text)
        if quantifier:
            triples.append((rule_uri, f"{INF_NS}quantifier", quantifier))

        log.info(
            "rdf_compilation_complete",
            rule_name=rule_name,
            triple_count=len(triples),
        )
        return triples


def _sanitize_uri(name: str) -> str:
    """Sanitize a name for use in a URI component."""
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", name)


def _infer_rule_type(rule_text: str) -> str:
    """
    Infer the rule type from rule text.

    Returns one of: AND, OR, ITERATE, CONCLUSION, or empty string.
    """
    lines = rule_text.strip().split("\n")
    for line in lines:
        stripped = line.strip().upper()
        if "ITERATE" in stripped:
            return "ITERATE"
        if re.search(r"\bOR\b", stripped):
            return "OR"
        if re.search(r"\bAND\b", stripped):
            return "AND"
    return "CONCLUSION"


def _extract_children(rule_text: str) -> List[str]:
    """
    Extract child node names from rule text.

    Parses dependency lines (indented lines below a rule header)
    and returns their names.
    """
    children = []
    lines = rule_text.strip().split("\n")
    for line in lines[1:]:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            name = stripped.split()[0] if stripped.split() else stripped
            if name:
                children.append(name)
    return children


def _extract_quantifier(rule_text: str) -> str:
    """Extract quantifier from iterate rule text, if present."""
    lines = rule_text.strip().split("\n")
    for line in lines:
        stripped = line.strip().upper()
        if "ITERATE" in stripped:
            tokens = stripped.split()
            for token in tokens:
                if token in ("ALL", "NONE", "SOME"):
                    return token
    return ""

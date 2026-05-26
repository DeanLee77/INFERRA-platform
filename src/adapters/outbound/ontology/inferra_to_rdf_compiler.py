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
    "NOT": f"{INF_NS}notDependsOn",
    "KNOWN": f"{INF_NS}knownDependsOn",
    "MANDATORY": f"{INF_NS}mandatoryDependsOn",
    "OPTIONALLY": f"{INF_NS}optionalDependsOn",
    "POSSIBLY": f"{INF_NS}possibleDependsOn",
    "ITERATE": f"{INF_NS}iteratesOver",
}

_IN_ITERATE_PATTERN = re.compile(
    r"^(?:NOT\s+ALL|NOT\s+NONE|AT\s+LEAST\s+\d+|AT\s+MOST\s+\d+|EXACTLY\s+\d+|EXACT\s+\d+|ALL|NONE|SOME|\d+)\s+.+?\s+IN\s+.+$",
    re.IGNORECASE,
)


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
        triples.append((rule_uri, RDF_TYPE, f"{INF_NS}RuleSet"))
        triples.append((rule_uri, f"{INF_NS}name", rule_name))
        triples.append((rule_uri, f"{INF_NS}sourceText", rule_text))
        triples.extend(_compile_rule_set_structure(rule_text, rule_uri))

        log.info(
            "rdf_compilation_complete",
            rule_name=rule_name,
            triple_count=len(triples),
        )
        return triples


def _sanitize_uri(name: str) -> str:
    """Sanitize a name for use in a URI component."""
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", name)


def _node_uri(rule_uri: str, name: str) -> str:
    return f"{rule_uri}/node/{_sanitize_uri(name)}"


def _declaration_uri(rule_uri: str, name: str) -> str:
    return f"{rule_uri}/declaration/{_sanitize_uri(name)}"


def _compile_rule_set_structure(rule_text: str, rule_uri: str) -> List[Tuple[str, str, str]]:
    triples: List[Tuple[str, str, str]] = []
    current_parent_uri = ""
    current_parent_type = ""

    for raw_line in rule_text.splitlines():
        if not raw_line.strip() or raw_line.strip().startswith("#"):
            continue

        stripped = raw_line.strip()
        indent = len(raw_line) - len(raw_line.lstrip(" "))

        import_match = re.match(r"^IMPORT:\s*(.+)$", stripped, re.IGNORECASE)
        if indent == 0 and import_match:
            imported_name = import_match.group(1).strip()
            imported_uri = f"{INF_NS}rule/{_sanitize_uri(imported_name)}"
            triples.append((rule_uri, f"{INF_NS}importsRuleSet", imported_uri))
            triples.append((imported_uri, RDF_TYPE, f"{INF_NS}RuleSet"))
            triples.append((imported_uri, f"{INF_NS}name", imported_name))
            continue

        declaration = _parse_declaration(stripped)
        if indent == 0 and declaration is not None:
            name, declaration_type, value_type = declaration
            declaration_uri = _declaration_uri(rule_uri, name)
            triples.append((rule_uri, f"{INF_NS}declares", declaration_uri))
            triples.append((declaration_uri, RDF_TYPE, f"{INF_NS}{declaration_type}Declaration"))
            triples.append((declaration_uri, f"{INF_NS}name", name))
            if value_type:
                triples.append((declaration_uri, f"{INF_NS}valueType", value_type))
            continue

        if indent == 0:
            current_parent_uri = _node_uri(rule_uri, stripped)
            current_parent_type = _infer_rule_type(stripped)
            triples.append((rule_uri, f"{INF_NS}containsNode", current_parent_uri))
            triples.append((current_parent_uri, RDF_TYPE, f"{INF_NS}RuleNode"))
            triples.append((current_parent_uri, RDF_TYPE, RULE_TYPES.get(current_parent_type, RULE_TYPES["CONCLUSION"])))
            triples.append((current_parent_uri, f"{INF_NS}name", stripped))
            quantifier = _extract_quantifier(stripped)
            if quantifier:
                triples.append((current_parent_uri, f"{INF_NS}quantifier", quantifier))
            continue

        if current_parent_uri:
            child_name, modifiers = _normalise_dependency_child(stripped)
            if not child_name:
                continue
            child_uri = _node_uri(rule_uri, child_name)
            dep_type = _dependency_type(modifiers, current_parent_type)
            predicate = DEPENDENCY_PREDICATES.get(dep_type, f"{INF_NS}dependsOn")
            if dep_type in {"AND", "OR", "ITERATE"} and current_parent_type == "CONCLUSION":
                triples.append((current_parent_uri, RDF_TYPE, RULE_TYPES[dep_type]))
            triples.append((current_parent_uri, predicate, child_uri))
            triples.append((child_uri, RDF_TYPE, f"{INF_NS}Node"))
            triples.append((child_uri, f"{INF_NS}name", child_name))
            for modifier in modifiers:
                triples.append((child_uri, f"{INF_NS}dependencyModifier", modifier))
            quantifier = _extract_quantifier(child_name)
            if quantifier:
                triples.append((child_uri, RDF_TYPE, RULE_TYPES["ITERATE"]))
                triples.append((child_uri, f"{INF_NS}quantifier", quantifier))

    return triples


def _parse_declaration(line: str) -> tuple[str, str, str] | None:
    match = re.match(r"^(FIXED|INPUT)\s+(.+?)(?:\s+(IS|AS)\s+(.+))?$", line, re.IGNORECASE)
    if not match:
        return None
    declaration_type = match.group(1).upper().title()
    name = match.group(2).strip()
    value_type = (match.group(4) or "").strip()
    return name, declaration_type, value_type


def _normalise_dependency_child(line: str) -> tuple[str, List[str]]:
    tokens = line.split()
    modifiers: List[str] = []
    while tokens:
        token = tokens[0].upper()
        if token in {"AND", "OR", "NOT", "KNOWN", "MANDATORY", "OPTIONALLY", "POSSIBLY", "NEEDS", "WANTS"}:
            modifiers.append(token)
            tokens.pop(0)
            continue
        break
    return " ".join(tokens).strip(), modifiers


def _dependency_type(modifiers: List[str], parent_type: str) -> str:
    for modifier in modifiers:
        if modifier in {"AND", "OR", "NOT", "KNOWN", "MANDATORY", "OPTIONALLY", "POSSIBLY"}:
            return modifier
    return parent_type if parent_type in {"AND", "OR", "ITERATE"} else ""


def _infer_rule_type(rule_text: str) -> str:
    """
    Infer the rule type from rule text.

    Returns one of: AND, OR, ITERATE, CONCLUSION, or empty string.
    """
    lines = rule_text.strip().split("\n")
    for line in lines:
        stripped = line.strip().upper()
        if "ITERATE" in stripped or _IN_ITERATE_PATTERN.match(stripped):
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
            name, _ = _normalise_dependency_child(stripped)
            if name:
                children.append(name)
    return children


def _extract_quantifier(rule_text: str) -> str:
    """Extract quantifier from iterate rule text, if present."""
    lines = rule_text.strip().split("\n")
    for line in lines:
        stripped = line.strip().upper()
        if "ITERATE" in stripped or _IN_ITERATE_PATTERN.match(stripped):
            tokens = stripped.split()
            if len(tokens) >= 2 and tokens[0] == "NOT" and tokens[1] in ("ALL", "NONE"):
                return f"{tokens[0]} {tokens[1]}"
            if len(tokens) >= 3 and tokens[0] == "AT" and tokens[1] == "LEAST" and tokens[2].isdigit():
                return f"AT LEAST {tokens[2]}"
            if len(tokens) >= 3 and tokens[0] == "AT" and tokens[1] == "MOST" and tokens[2].isdigit():
                return f"AT MOST {tokens[2]}"
            if len(tokens) >= 2 and tokens[0] in ("EXACT", "EXACTLY") and tokens[1].isdigit():
                return f"EXACTLY {tokens[1]}"
            for token in tokens:
                if token in ("ALL", "NONE", "SOME"):
                    return token
                if token.isdigit():
                    return token
    return ""

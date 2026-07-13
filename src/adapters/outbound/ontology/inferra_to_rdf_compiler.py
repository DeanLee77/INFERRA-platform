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
from dataclasses import dataclass
from typing import List, Tuple

import structlog

log = structlog.get_logger()

INF_NS = "http://inferra.ai/schema#"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
COMPILER_VERSION = "inferra-rdf-compiler-v2"

RULE_TYPES = {
    "AND": f"{INF_NS}AndRule",
    "OR": f"{INF_NS}OrRule",
    "ITERATE": f"{INF_NS}IterateRule",
    "CALC": f"{INF_NS}CalculationNode",
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
    "REQUIRES": f"{INF_NS}requiresVariable",
}

METADATA_PREDICATES = {
    "REFERENCE": f"{INF_NS}statutoryReference",
    "SECTION": f"{INF_NS}statutorySection",
    "ORIGINAL": f"{INF_NS}originalText",
}

_IN_ITERATE_PATTERN = re.compile(
    r"^(?:NOT\s+ALL|NOT\s+NONE|AT\s+LEAST\s+\d+|AT\s+MOST\s+\d+|EXACTLY\s+\d+|EXACT\s+\d+|ALL|NONE|SOME|\d+)\s+.+?\s+IN\s+.+$",
    re.IGNORECASE,
)
_COMPARISON_PATTERN = re.compile(
    r"^(?P<left>[\w\s]+?)\s*(?P<operator><=|>=|=|<|>|IS\s+IN\s+LIST)\s*(?P<right>.+)$",
    re.IGNORECASE,
)
_CALC_PATTERN = re.compile(r"^(?P<name>.+?)\s+IS\s+CALC\s+(?P<formula>.+)$", re.IGNORECASE)


@dataclass(frozen=True)
class _NodeContext:
    indent: int
    uri: str
    rule_type: str


@dataclass(frozen=True)
class _ListContext:
    indent: int
    uri: str


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
    parent_stack: list[_NodeContext] = []
    declarations: dict[str, str] = {}
    list_context: _ListContext | None = None
    pending_metadata: dict[str, list[str]] = {}

    for raw_line in rule_text.splitlines():
        if not raw_line.strip():
            list_context = None
            continue

        stripped = raw_line.strip()
        indent = len(raw_line) - len(raw_line.lstrip(" "))

        metadata = _parse_metadata_comment(stripped)
        if metadata is not None:
            key, value = metadata
            pending_metadata.setdefault(key, []).append(value)
            list_context = None
            continue

        if stripped.startswith("#"):
            list_context = None
            continue

        item_value = _parse_list_item(stripped)
        if item_value is not None:
            if list_context is not None and indent > list_context.indent:
                triples.append((list_context.uri, f"{INF_NS}hasItem", item_value))
            continue

        list_context = None

        import_match = re.match(r"^IMPORT:\s*(.+)$", stripped, re.IGNORECASE)
        if indent == 0 and import_match:
            parent_stack = []
            imported_name = import_match.group(1).strip()
            imported_uri = f"{INF_NS}rule/{_sanitize_uri(imported_name)}"
            triples.append((rule_uri, f"{INF_NS}importsRuleSet", imported_uri))
            triples.append((imported_uri, RDF_TYPE, f"{INF_NS}RuleSet"))
            triples.append((imported_uri, f"{INF_NS}name", imported_name))
            continue

        declaration = _parse_declaration(stripped)
        if indent == 0 and declaration is not None:
            parent_stack = []
            name, declaration_type, value_type = declaration
            declaration_uri = _declaration_uri(rule_uri, name)
            declarations[_declaration_key(name)] = declaration_uri
            triples.append((rule_uri, f"{INF_NS}declares", declaration_uri))
            triples.append((declaration_uri, RDF_TYPE, f"{INF_NS}{declaration_type}Declaration"))
            triples.append((declaration_uri, f"{INF_NS}name", name))
            if value_type:
                triples.append((declaration_uri, f"{INF_NS}valueType", value_type))
            if value_type.upper() == "LIST":
                triples.append((declaration_uri, RDF_TYPE, f"{INF_NS}EnumList"))
                list_context = _ListContext(indent=indent, uri=declaration_uri)
            continue

        if indent == 0:
            parent_name = _rule_node_name(stripped)
            parent_uri = _node_uri(rule_uri, parent_name)
            parent_type = _infer_rule_type(stripped)
            triples.append((rule_uri, f"{INF_NS}containsNode", parent_uri))
            _append_rule_node_triples(
                triples,
                parent_uri,
                stripped,
                parent_type,
                rule_uri,
                declarations,
                pending_metadata,
            )
            pending_metadata = {}
            parent_stack = [_NodeContext(indent=indent, uri=parent_uri, rule_type=parent_type)]
            continue

        while parent_stack and indent <= parent_stack[-1].indent:
            parent_stack.pop()

        if not parent_stack:
            continue

        parent = parent_stack[-1]
        child_name, modifiers = _normalise_dependency_child(stripped)
        if not child_name:
            continue

        child_node_name = _rule_node_name(child_name)
        child_type = _infer_rule_type(child_name)
        dep_type = _dependency_type(modifiers, parent.rule_type)
        predicate = DEPENDENCY_PREDICATES.get(dep_type, f"{INF_NS}dependsOn")
        if dep_type == "REQUIRES":
            variable_uri = _resolve_variable_uri(rule_uri, child_node_name, declarations)
            triples.append((parent.uri, predicate, variable_uri))
            if _declaration_key(child_node_name) not in declarations:
                _append_variable_triples(triples, variable_uri, child_node_name)
            continue

        child_uri = _node_uri(rule_uri, child_node_name)
        if dep_type in {"AND", "OR", "ITERATE"} and parent.rule_type == "CONCLUSION":
            triples.append((parent.uri, RDF_TYPE, RULE_TYPES[dep_type]))
        triples.append((parent.uri, predicate, child_uri))
        triples.append((child_uri, RDF_TYPE, f"{INF_NS}Node"))
        _append_rule_node_triples(
            triples,
            child_uri,
            child_name,
            child_type,
            rule_uri,
            declarations,
            pending_metadata,
        )
        pending_metadata = {}
        for modifier in _emitted_dependency_modifiers(modifiers):
            triples.append((child_uri, f"{INF_NS}dependencyModifier", modifier))

        parent_stack.append(_NodeContext(indent=indent, uri=child_uri, rule_type=child_type))

    return triples


def _append_rule_node_triples(
    triples: List[Tuple[str, str, str]],
    node_uri: str,
    node_text: str,
    rule_type: str,
    rule_uri: str,
    declarations: dict[str, str],
    metadata: dict[str, list[str]] | None = None,
) -> None:
    node_name = _rule_node_name(node_text)
    triples.append((node_uri, RDF_TYPE, f"{INF_NS}RuleNode"))
    triples.append((node_uri, RDF_TYPE, RULE_TYPES.get(rule_type, RULE_TYPES["CONCLUSION"])))
    triples.append((node_uri, f"{INF_NS}name", node_name))
    calc = _parse_calculation(node_text)
    if calc is not None:
        _, formula = calc
        triples.append((node_uri, f"{INF_NS}hasFormula", formula))
    _append_comparison_triples(triples, node_uri, node_text, rule_uri, declarations)
    quantifier = _extract_quantifier(node_text)
    if quantifier:
        triples.append((node_uri, f"{INF_NS}quantifier", quantifier))
    if metadata:
        _append_metadata_triples(triples, node_uri, metadata)


def _parse_declaration(line: str) -> tuple[str, str, str] | None:
    match = re.match(r"^(FIXED|INPUT)\s+(.+?)(?:\s+(IS|AS)\s+(.+))?$", line, re.IGNORECASE)
    if not match:
        return None
    declaration_type = match.group(1).upper().title()
    name = match.group(2).strip()
    value_type = (match.group(4) or "").strip()
    return name, declaration_type, value_type


def _declaration_key(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip()).casefold()


def _parse_metadata_comment(line: str) -> tuple[str, str] | None:
    match = re.match(r"^#\s*(Reference|Section|Original):\s*(.*)$", line, re.IGNORECASE)
    if not match:
        return None
    return match.group(1).upper(), match.group(2).strip()


def _append_metadata_triples(
    triples: List[Tuple[str, str, str]],
    node_uri: str,
    metadata: dict[str, list[str]],
) -> None:
    for key, values in metadata.items():
        predicate = METADATA_PREDICATES.get(key)
        if not predicate:
            continue
        for value in values:
            triples.append((node_uri, predicate, value))


def _parse_list_item(line: str) -> str | None:
    match = re.match(r"^ITEM:?\s+(.+)$", line, re.IGNORECASE)
    if not match:
        return None
    return match.group(1).strip()


def _parse_calculation(line: str) -> tuple[str, str] | None:
    match = _CALC_PATTERN.match(line.strip())
    if not match:
        return None
    return match.group("name").strip(), match.group("formula").strip()


def _rule_node_name(rule_text: str) -> str:
    calc = _parse_calculation(rule_text)
    if calc is not None:
        name, _ = calc
        return name
    return rule_text.strip()


def _parse_comparison(line: str) -> tuple[str, str, str] | None:
    match = _COMPARISON_PATTERN.match(line.strip())
    if not match:
        return None
    operator = re.sub(r"\s+", " ", match.group("operator").upper())
    right = match.group("right").strip()
    if operator == "IS IN LIST" and right.startswith(":"):
        right = right[1:].strip()
    return match.group("left").strip(), operator, right


def _append_comparison_triples(
    triples: List[Tuple[str, str, str]],
    node_uri: str,
    node_text: str,
    rule_uri: str,
    declarations: dict[str, str],
) -> None:
    comparison = _parse_comparison(node_text)
    if comparison is None:
        return

    left, operator, right = comparison
    left_uri = _resolve_variable_uri(rule_uri, left, declarations)
    triples.append((node_uri, RDF_TYPE, f"{INF_NS}ComparisonNode"))
    triples.append((node_uri, f"{INF_NS}dependencyProperty", left_uri))
    triples.append((node_uri, f"{INF_NS}operator", operator))
    triples.append((node_uri, f"{INF_NS}comparesTo", _resolve_comparison_value(right, declarations)))
    if _declaration_key(left) not in declarations:
        _append_variable_triples(triples, left_uri, left)


def _resolve_variable_uri(rule_uri: str, name: str, declarations: dict[str, str]) -> str:
    return declarations.get(_declaration_key(name)) or _declaration_uri(rule_uri, name)


def _resolve_comparison_value(value: str, declarations: dict[str, str]) -> str:
    declaration_uri = declarations.get(_declaration_key(value))
    if declaration_uri is not None:
        return declaration_uri
    return value.strip().strip("\"'")


def _append_variable_triples(
    triples: List[Tuple[str, str, str]],
    variable_uri: str,
    name: str,
) -> None:
    triples.append((variable_uri, RDF_TYPE, f"{INF_NS}Variable"))
    triples.append((variable_uri, f"{INF_NS}name", name))


def _emitted_dependency_modifiers(modifiers: List[str]) -> List[str]:
    return [modifier for modifier in modifiers if modifier not in {"NOT", "NEEDS"}]


def _normalise_dependency_child(line: str) -> tuple[str, List[str]]:
    line = line.strip()
    modifiers: List[str] = []

    for pattern in (
        r"^(OR|AND)\b\s*",
        r"^(MANDATORY|OPTIONALLY|POSSIBLY)\b\s*",
    ):
        match = re.match(pattern, line, flags=re.IGNORECASE)
        if match:
            modifiers.append(match.group(1).upper())
            line = line[match.end():].strip()

    while True:
        match = re.match(r"^(NOT|KNOWN)\b\s*", line, flags=re.IGNORECASE)
        if match is None:
            break
        if match.group(1).upper() == "NOT" and re.match(
            r"^NOT\s+(ALL|NONE)\b",
            line,
            flags=re.IGNORECASE,
        ):
            break
        modifiers.append(match.group(1).upper())
        line = line[match.end():].strip()

    match = re.match(r"^(NEEDS|WANTS)\b\s*", line, flags=re.IGNORECASE)
    if match:
        modifiers.append(match.group(1).upper())
        line = line[match.end():].strip()

    return line, modifiers


def _dependency_type(modifiers: List[str], parent_type: str) -> str:
    if "NOT" in modifiers:
        return "NOT"
    if "KNOWN" in modifiers:
        return "KNOWN"
    if "NEEDS" in modifiers:
        return "REQUIRES"
    for modifier in modifiers:
        if modifier in {"AND", "OR", "NOT", "KNOWN", "MANDATORY", "OPTIONALLY", "POSSIBLY"}:
            return modifier
        if modifier == "WANTS":
            return "OR"
    return parent_type if parent_type in {"AND", "OR", "ITERATE"} else ""


def _infer_rule_type(rule_text: str) -> str:
    """
    Infer the rule type from rule text.

    Returns one of: AND, OR, ITERATE, CONCLUSION, or empty string.
    """
    if _parse_calculation(rule_text) is not None:
        return "CALC"
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

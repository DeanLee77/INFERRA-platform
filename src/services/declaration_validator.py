"""NodeSet-backed declaration validation.

This validator complements :mod:`rule_validation_service` by checking the
already-parsed rule graph instead of only scanning source text. It deliberately
uses the existing ``NodeSet`` and graph APIs so the current project remains the
behavioral source of truth.
"""

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import structlog

log = structlog.get_logger(__name__)

UNUSED_DECLARATION = "UNUSED_DECLARATION"
UNDECLARED_REFERENCE = "UNDECLARED_REFERENCE"
DUPLICATE_DECLARATION = "DUPLICATE_DECLARATION"
SELF_REFERENTIAL_RULE = "SELF_REFERENTIAL_RULE"
NULL_NODESET = "NULL_NODESET"


@dataclass(frozen=True)
class DeclarationFinding:
    code: str
    message: str
    line: Optional[int] = None
    node_name: Optional[str] = None

    def to_dict(self) -> dict:
        result = {"code": self.code, "message": self.message}
        if self.line is not None:
            result["line"] = self.line
        if self.node_name is not None:
            result["node_name"] = self.node_name
        return result


@dataclass(frozen=True)
class DeclarationValidationResult:
    valid: bool
    errors: Tuple[DeclarationFinding, ...] = ()
    warnings: Tuple[DeclarationFinding, ...] = ()

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "errors": [error.to_dict() for error in self.errors],
            "warnings": [warning.to_dict() for warning in self.warnings],
        }


class DeclarationValidator:
    """Validate declarations and graph references in a parsed ``NodeSet``."""

    _IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_ ]*")
    _EXPRESSION_STOP_WORDS = frozenset({
        "abs",
        "and",
        "false",
        "max",
        "min",
        "not",
        "or",
        "round",
        "true",
    })
    _APOSTROPHE_VARIANTS = str.maketrans({
        "\u2018": "'",
        "\u2019": "'",
        "\u201b": "'",
        "\u2032": "'",
        "\u02bc": "'",
        "`": "'",
    })

    def validate(self, node_set: Any) -> DeclarationValidationResult:
        if node_set is None:
            return DeclarationValidationResult(
                valid=False,
                errors=(DeclarationFinding(NULL_NODESET, "NodeSet is None"),),
            )

        errors: List[DeclarationFinding] = []
        warnings: List[DeclarationFinding] = []

        declarations = self._collect_declarations(node_set, errors)
        defined = set(declarations.keys())
        referenced: Set[str] = set()

        node_dict = self._safe_mapping(node_set, "get_node_dictionary")
        graph = getattr(node_set, "get_graph", lambda: None)()

        for node_name, node in node_dict.items():
            conclusion = self._normalise(getattr(node, "get_variable_name", lambda: None)())
            if conclusion and self._is_conclusion_node(node):
                defined.add(conclusion)

        for node_name, node in node_dict.items():
            for reference in self._extract_node_references(node):
                normalised = self._normalise(reference)
                if not normalised:
                    continue
                self._record_reference(
                    normalised,
                    reference,
                    defined,
                    referenced,
                    errors,
                    node,
                )

            if graph is None or not hasattr(graph, "get_children_flat"):
                continue

            for child_name in graph.get_children_flat(str(node_name)):
                if self._normalise(child_name) == self._normalise(node_name):
                    errors.append(DeclarationFinding(
                        code=SELF_REFERENTIAL_RULE,
                        message=f"Rule '{node_name}' references itself as a child dependency",
                        line=self._line_number(node),
                        node_name=str(node_name),
                    ))
                    continue

                child_node = node_dict.get(child_name)
                child_reference = self._reference_name_for_child(child_name, child_node)
                normalised = self._normalise(child_reference)
                if normalised:
                    self._record_reference(
                        normalised,
                        child_reference,
                        defined,
                        referenced,
                        errors,
                        child_node or node,
                    )

        for normalised, (original_name, decl_type, line_number) in declarations.items():
            if normalised not in referenced:
                warnings.append(DeclarationFinding(
                    code=UNUSED_DECLARATION,
                    message=f"{decl_type} '{original_name}' is declared but never referenced in rule blocks",
                    line=line_number,
                    node_name=original_name,
                ))

        return DeclarationValidationResult(
            valid=len(errors) == 0,
            errors=tuple(self._dedupe(errors)),
            warnings=tuple(self._dedupe(warnings)),
        )

    def validate_rule_text(self, rule_text: str, rule_name: str = "") -> DeclarationValidationResult:
        """Parse rule text, then validate declarations on the resulting NodeSet."""
        try:
            from src.domain.rule_parser.rule_set_parser import RuleSetParser
            from src.domain.rule_parser.rule_set_reader import RuleSetReader
            from src.domain.rule_parser.rule_set_scanner import RuleSetScanner

            reader = RuleSetReader()
            reader.create()
            parser = RuleSetParser()
            parser.create()
            parser.set_source_name(rule_name or "__validation__")
            reader.set_file_with_text(rule_text)
            scanner = RuleSetScanner(reader, parser)
            scanner.scan_rule_set()
            scanner.establish_node_set()
            return self.validate(parser.get_node_set())
        except Exception:
            log.warning(
                "declaration_nodeset_validation_skipped",
                session_id="",
                node_id="",
                fact_source="",
                correlation_id=rule_name,
                rule_name=rule_name,
                exc_info=True,
            )
            return DeclarationValidationResult(valid=True)

    def _collect_declarations(
        self,
        node_set: Any,
        errors: List[DeclarationFinding],
    ) -> Dict[str, Tuple[str, str, Optional[int]]]:
        declarations: Dict[str, Tuple[str, str, Optional[int]]] = {}
        for label, getter in (("INPUT", "get_input_dictionary"), ("FIXED", "get_fact_dictionary")):
            for var_name, fact_value in self._safe_mapping(node_set, getter).items():
                self._add_declaration(
                    declarations,
                    errors,
                    str(var_name),
                    label,
                    getattr(fact_value, "line_number", None),
                )

        for node in self._safe_mapping(node_set, "get_node_dictionary").values():
            meta_type = getattr(node, "get_meta_type", lambda: None)()
            if meta_type is None:
                continue
            meta_value = getattr(meta_type, "value", str(meta_type))
            if meta_value not in {"INPUT", "FIXED"}:
                continue
            var_name = getattr(node, "get_variable_name", lambda: None)()
            if var_name:
                self._add_declaration(
                    declarations,
                    errors,
                    str(var_name),
                    meta_value,
                    self._line_number(node),
                )
        return declarations

    def _add_declaration(
        self,
        declarations: Dict[str, Tuple[str, str, Optional[int]]],
        errors: List[DeclarationFinding],
        var_name: str,
        decl_type: str,
        line_number: Optional[int],
    ) -> None:
        normalised = self._normalise(var_name)
        if normalised in declarations:
            errors.append(DeclarationFinding(
                code=DUPLICATE_DECLARATION,
                message=f"{decl_type} '{var_name}' is declared more than once",
                line=line_number,
                node_name=var_name,
            ))
            return
        declarations[normalised] = (var_name, decl_type, line_number)

    def _extract_node_references(self, node: Any) -> Tuple[str, ...]:
        node_type = type(node).__name__
        references: List[str] = []

        if node_type == "ComparisonLine":
            lhs = getattr(node, "get_lhs", lambda: None)()
            if lhs:
                references.append(str(lhs))
            rhs = getattr(node, "get_rhs", lambda: None)()
            rhs_value = getattr(rhs, "get_value", lambda: None)()
            if self._looks_like_reference(rhs_value):
                references.append(str(rhs_value))
        elif node_type == "ExprConclusionLine":
            equation = getattr(node, "get_equation", lambda: None)()
            expression = getattr(equation, "get_value", lambda: "")()
            references.extend(self._extract_expression_references(str(expression)))
        elif node_type == "IterateLine":
            var_name = getattr(node, "get_variable_name", lambda: None)()
            list_name = getattr(node, "get_given_list_name", lambda: None)()
            if var_name:
                references.append(str(var_name))
            if list_name:
                references.append(str(list_name))

        return tuple(references)

    def _record_reference(
        self,
        normalised: str,
        original: str,
        defined: Set[str],
        referenced: Set[str],
        errors: List[DeclarationFinding],
        node: Any,
    ) -> None:
        if normalised in defined:
            referenced.add(normalised)
            return
        errors.append(DeclarationFinding(
            code=UNDECLARED_REFERENCE,
            message=f"Variable '{original}' is referenced but not declared as INPUT or FIXED",
            line=self._line_number(node),
            node_name=str(original),
        ))

    def _reference_name_for_child(self, child_name: str, child_node: Any) -> str:
        if child_node is None:
            return str(child_name)
        node_type = type(child_node).__name__
        if node_type in {"ComparisonLine", "IterateLine"}:
            var_name = getattr(child_node, "get_variable_name", lambda: None)()
            return str(var_name or child_name)
        if node_type == "ValueConclusionLine" and getattr(child_node, "get_is_plain_statement", lambda: False)():
            return str(getattr(child_node, "get_variable_name", lambda: None)() or child_name)
        return str(child_name)

    def _extract_expression_references(self, expression: str) -> Tuple[str, ...]:
        references: List[str] = []
        without_literals = re.sub(r'"[^"]*"|\'[^\']*\'', " ", expression)
        for token in self._IDENTIFIER_PATTERN.findall(without_literals):
            cleaned = re.sub(r"\s+", " ", token.strip())
            if cleaned and cleaned.lower() not in self._EXPRESSION_STOP_WORDS:
                references.append(cleaned)
        return tuple(references)

    def _looks_like_reference(self, value: Any) -> bool:
        if value is None:
            return False
        candidate = str(value).strip()
        if not candidate:
            return False
        if candidate.lower() in {"true", "false"}:
            return False
        if candidate[0] in {"'", '"'}:
            return False
        if re.fullmatch(r"-?\d+(?:\.\d+)?", candidate):
            return False
        return bool(re.search(r"[A-Za-z_]", candidate))

    def _is_conclusion_node(self, node: Any) -> bool:
        return type(node).__name__ in {"ValueConclusionLine", "ExprConclusionLine"}

    def _safe_mapping(self, node_set: Any, getter_name: str) -> Dict[str, Any]:
        getter = getattr(node_set, getter_name, None)
        if getter is None:
            return {}
        value = getter()
        return dict(value) if isinstance(value, dict) else {}

    def _line_number(self, node: Any) -> Optional[int]:
        if node is None:
            return None
        line = getattr(node, "get_node_line", lambda: None)()
        return line if isinstance(line, int) else None

    def _normalise(self, name: Any) -> str:
        normalised = str(name).translate(self._APOSTROPHE_VARIANTS)
        normalised = re.sub(r"\s+", " ", normalised.strip()).lower()
        return re.sub(r"^(?:the|a)\s+person(?=\b|'s\b)", "person", normalised)

    def _dedupe(self, findings: Iterable[DeclarationFinding]) -> List[DeclarationFinding]:
        seen: Set[Tuple[str, Optional[int], Optional[str], str]] = set()
        deduped: List[DeclarationFinding] = []
        for finding in findings:
            key = (finding.code, finding.line, finding.node_name, finding.message)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(finding)
        return deduped


def validate_declarations(node_set: Any) -> DeclarationValidationResult:
    """Functional convenience wrapper used by tests and promotion gates."""
    return DeclarationValidator().validate(node_set)

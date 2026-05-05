"""
Rule Validation Service Module.
Synchronous pre-save gate that validates rule text before persistence.
Implements content-hash caching with LRU eviction and TTL expiry.
"""

import hashlib
import re
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

import structlog

from src.domain.fact_values import FactValueType

_logger = structlog.get_logger("inferra.rule_validation")


# =============================================================================
# Value Objects
# =============================================================================

@dataclass(frozen=True)
class ValidationEntry:
    """Base for a single validation error or warning."""
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
class ValidationError(ValidationEntry):
    """A single validation error."""

    def __repr__(self) -> str:
        return f"ValidationError(code={self.code!r}, message={self.message!r}, line={self.line})"


@dataclass(frozen=True)
class ValidationWarning(ValidationEntry):
    """A single validation warning."""

    def __repr__(self) -> str:
        return f"ValidationWarning(code={self.code!r}, message={self.message!r}, line={self.line})"


@dataclass(frozen=True)
class ValidationResult:
    """Result of a validation run. Errors and warnings are tuples (immutable)."""
    valid: bool
    errors: Tuple[ValidationError, ...] = ()
    warnings: Tuple[ValidationWarning, ...] = ()

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
        }

    def __repr__(self) -> str:
        return f"ValidationResult(valid={self.valid}, errors={len(self.errors)}, warnings={len(self.warnings)})"


# =============================================================================
# Validation Service
# =============================================================================

class RuleValidationService:
    """
    Synchronous pre-save gate that validates rule text.

    Validation checks (Phase 1):
    1. Syntax & Tokeniser — line-by-line structural validation
    2. Type Consistency — INPUT/FIXED declarations vs rule block usage
    3. Import Resolution — placeholder (Phase 2: RuleSetImportResolver)
    4. DAG Cycle Check — dependency graph must be acyclic

    Content-hash cache:
    - Key: SHA-256 of rule_text
    - Value: (timestamp, ValidationResult)
    - Eviction: LRU when cache exceeds maxsize; TTL expiry (default 300s)
    """

    _FIXED_PATTERN = re.compile(r"^(FIXED)\s+(.+?)(?:\s+(IS|AS)\s+.+)$")
    _INPUT_PATTERN = re.compile(r"^(INPUT)\s+(.+?)(?:\s+(AS|IS)\s+.+)$")
    _VALUE_CONCLUSION_PATTERN = re.compile(r"^(.+?)\s+IS\s+.+$")
    _EXPR_CONCLUSION_PATTERN = re.compile(r"^(.+?)\s+IS\s+CALC\s+.+$")
    _COMPARISON_PATTERN = re.compile(r"^(.+?)\s*(<=|>=|<|>|=)\s*.+$")
    _ITERATE_PATTERN = re.compile(r"^(.+?)\s+FOR\s+.+$")
    _COMMENT_PATTERN = re.compile(r"^(#|//)")
    _INDENTED_LINE_PATTERN = re.compile(r"^(\s+)(.+)$")
    _QUANTIFIER_PATTERN = re.compile(r"^(AND|OR)\s*(MANDATORY|OPTIONALLY|POSSIBLY)?\s*(NOT|KNOWN)?\s*")

    _NUMERIC_OPERATORS = frozenset({">", ">=", "<", "<="})

    _NUMERIC_TYPES = frozenset({
        FactValueType.INTEGER.value,
        FactValueType.DOUBLE.value,
        FactValueType.DECIMAL.value,
    })

    def __init__(self, cache_maxsize: int = 512, cache_ttl_seconds: int = 300):
        self._cache: OrderedDict[str, Tuple[float, ValidationResult]] = OrderedDict()
        self._cache_maxsize = cache_maxsize
        self._cache_ttl = cache_ttl_seconds

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def validate(self, rule_text: str, rule_name: str = "") -> ValidationResult:
        if not rule_text or not rule_text.strip():
            return ValidationResult(
                valid=False,
                errors=(ValidationError("EMPTY_RULE", "Rule text is empty"),),
            )

        content_hash = self._compute_content_hash(rule_text)
        cached = self._get_cached(content_hash)
        if cached is not None:
            _logger.debug("validation_cache_hit", rule_name=rule_name)
            return cached

        errors: List[ValidationError] = []
        warnings: List[ValidationWarning] = []

        parsed = self._check_syntax(rule_text, errors, warnings)
        if errors:
            result = ValidationResult(valid=False, errors=tuple(errors), warnings=tuple(warnings))
            self._set_cached(content_hash, result)
            return result

        self._check_type_consistency(parsed, errors, warnings)

        self._check_dag_cycles(parsed, errors)

        result = ValidationResult(valid=len(errors) == 0, errors=tuple(errors), warnings=tuple(warnings))
        self._set_cached(content_hash, result)
        _logger.info(
            "validation_complete",
            rule_name=rule_name,
            valid=result.valid,
            error_count=len(errors),
            warning_count=len(warnings),
        )
        return result

    def invalidate_cache(self) -> None:
        """Evict all cached validation results."""
        self._cache.clear()
        _logger.debug("validation_cache_invalidated")

    # -------------------------------------------------------------------------
    # Check 1: Syntax & Tokeniser
    # -------------------------------------------------------------------------

    def _check_syntax(
        self,
        rule_text: str,
        errors: List[ValidationError],
        warnings: List[ValidationWarning],
    ) -> Dict:
        declarations: Dict[str, dict] = {}
        rules: List[dict] = []
        in_list = False
        list_var_name = ""
        line_number = 0

        for raw_line in rule_text.splitlines():
            line_number += 1
            stripped = raw_line.strip()

            if not stripped or self._COMMENT_PATTERN.match(stripped):
                in_list = False
                continue

            if in_list and stripped.startswith("ITEM"):
                continue

            indent_match = self._INDENTED_LINE_PATTERN.match(raw_line)
            if indent_match:
                child_text = indent_match.group(2).strip()
                child_clean = self._QUANTIFIER_PATTERN.sub("", child_text).strip()
                if child_clean:
                    self._parse_rule_line(child_clean, line_number, declarations, rules, errors)
                continue

            fixed_match = self._FIXED_PATTERN.match(stripped)
            if fixed_match:
                var_name = fixed_match.group(2).strip()
                if var_name in declarations:
                    errors.append(ValidationError(
                        code="DUPLICATE_DECLARATION",
                        message=f"Variable '{var_name}' is declared more than once",
                        line=line_number,
                        node_name=var_name,
                    ))
                else:
                    declarations[var_name] = {
                        "type": "FIXED",
                        "value_type": self._extract_value_type(stripped, "FIXED"),
                        "line": line_number,
                        "meta": "FIXED",
                    }
                in_list = "AS LIST" in stripped or "IS LIST" in stripped
                list_var_name = var_name if in_list else ""
                continue

            input_match = self._INPUT_PATTERN.match(stripped)
            if input_match:
                var_name = input_match.group(2).strip()
                if var_name in declarations:
                    errors.append(ValidationError(
                        code="DUPLICATE_DECLARATION",
                        message=f"Variable '{var_name}' is declared more than once",
                        line=line_number,
                        node_name=var_name,
                    ))
                else:
                    declarations[var_name] = {
                        "type": "INPUT",
                        "value_type": self._extract_value_type(stripped, "INPUT"),
                        "line": line_number,
                        "meta": "INPUT",
                    }
                in_list = "AS LIST" in stripped
                list_var_name = var_name if in_list else ""
                continue

            in_list = False
            self._parse_rule_line(stripped, line_number, declarations, rules, errors)

        return {
            "declarations": declarations,
            "rules": rules,
            "lines": line_number,
        }

    _KEYWORDS = frozenset({
        "IS", "AS", "CALC", "FOR", "ALL", "NONE", "SOME",
        "AND", "OR", "NOT", "KNOWN", "MANDATORY", "OPTIONALLY", "POSSIBLY",
        "NEEDS", "WANTS", "ITEM", "INPUT", "FIXED", "IF",
        "IN", "LIST", "TRUE", "FALSE",
    })

    def _extract_references(self, raw: str, conclusion_var: str) -> List[str]:
        """
        Extract variable references from a rule line's raw text.

        Returns a list of potential variable names found in the text,
        excluding the conclusion variable itself and INFERRA keywords.
        Variable names that happen to be short uppercase (e.g., RATE,
        FLAG) are NOT excluded — only tokens in the _KEYWORDS set are
        filtered. This is a heuristic; false positives are possible for
        tokens that are neither declared nor rule conclusions (they'll
        trigger UNDECLARED_REFERENCE errors that can be reviewed).
        """
        tokens = re.findall(r'[A-Za-z_][A-Za-z0-9_]*', raw)
        refs = []
        for token in tokens:
            if token == conclusion_var:
                continue
            if token.upper() in self._KEYWORDS:
                continue
            refs.append(token)
        return refs

    def _parse_rule_line(
        self,
        text: str,
        line_number: int,
        declarations: Dict[str, dict],
        rules: List[dict],
        errors: List[ValidationError],
    ) -> None:
        expr_match = self._EXPR_CONCLUSION_PATTERN.match(text)
        if expr_match:
            var_name = expr_match.group(1).strip()
            refs = self._extract_references(text, var_name)
            rules.append({"line": line_number, "variable_name": var_name, "kind": "EXPR_CONCLUSION", "raw": text, "references": refs})
            return

        comp_match = self._COMPARISON_PATTERN.match(text)
        if comp_match:
            var_name = comp_match.group(1).strip()
            operator = comp_match.group(2).strip()
            refs = self._extract_references(text, var_name)
            rules.append({"line": line_number, "variable_name": var_name, "kind": "COMPARISON", "raw": text, "operator": operator, "references": refs})
            return

        iter_match = self._ITERATE_PATTERN.match(text)
        if iter_match:
            var_name = iter_match.group(1).strip()
            refs = self._extract_references(text, var_name)
            rules.append({"line": line_number, "variable_name": var_name, "kind": "ITERATE", "raw": text, "references": refs})
            return

        vc_match = self._VALUE_CONCLUSION_PATTERN.match(text)
        if vc_match:
            var_name = vc_match.group(1).strip()
            refs = self._extract_references(text, var_name)
            rules.append({"line": line_number, "variable_name": var_name, "kind": "VALUE_CONCLUSION", "raw": text, "references": refs})
            return

        var_name = text.strip()
        refs = self._extract_references(text, var_name)
        rules.append({"line": line_number, "variable_name": var_name, "kind": "PLAIN_STATEMENT", "raw": text, "references": refs})

    def _extract_value_type(self, line: str, meta: str) -> str:
        as_match = re.search(r"\bAS\s+(\w+)", line)
        if as_match:
            type_str = as_match.group(1).strip().upper()
            type_map = {
                "BOOLEAN": FactValueType.BOOLEAN.value,
                "BOOL": FactValueType.BOOLEAN.value,
                "TEXT": FactValueType.TEXT.value,
                "STRING": FactValueType.STRING.value,
                "NUMBER": FactValueType.DOUBLE.value,
                "INTEGER": FactValueType.INTEGER.value,
                "INT": FactValueType.INTEGER.value,
                "DECIMAL": FactValueType.DECIMAL.value,
                "DOUBLE": FactValueType.DOUBLE.value,
                "DATE": FactValueType.DATE.value,
                "LIST": FactValueType.LIST.value,
                "URL": FactValueType.URL.value,
                "HASH": FactValueType.HASH.value,
                "GUID": FactValueType.GUID.value,
            }
            return type_map.get(type_str, "UNKNOWN")
        is_match = re.search(r"\bIS\s+(.+)$", line)
        if is_match:
            value_str = is_match.group(1).strip()
            if value_str.startswith('"') or value_str.startswith("'"):
                return FactValueType.STRING.value
            try:
                int(value_str)
                return FactValueType.INTEGER.value
            except ValueError:
                pass
            try:
                float(value_str)
                return FactValueType.DOUBLE.value
            except ValueError:
                pass
            if value_str.lower() in ("true", "false"):
                return FactValueType.BOOLEAN.value
        return "UNKNOWN"

    # -------------------------------------------------------------------------
    # Check 2: Type Consistency
    # -------------------------------------------------------------------------

    def _check_type_consistency(
        self,
        parsed: Dict,
        errors: List[ValidationError],
        warnings: List[ValidationWarning],
    ) -> None:
        declarations = parsed["declarations"]
        rules = parsed["rules"]

        referenced_vars: Set[str] = set()
        all_referenced_names: Set[str] = set()
        rule_conclusion_names = {r["variable_name"] for r in rules}

        for rule in rules:
            var_name = rule["variable_name"]
            referenced_vars.add(var_name)
            all_referenced_names.add(var_name)

            for ref in rule.get("references", []):
                all_referenced_names.add(ref)

            if rule["kind"] == "COMPARISON":
                operator = rule.get("operator", "")
                decl = declarations.get(var_name)
                if decl and decl["value_type"] == FactValueType.BOOLEAN.value and operator in self._NUMERIC_OPERATORS:
                    errors.append(ValidationError(
                        code="TYPE_MISMATCH",
                        message=f"Variable '{var_name}' is declared as BOOLEAN but used with numeric operator '{operator}'",
                        line=rule["line"],
                        node_name=var_name,
                    ))

        declared_names = set(declarations.keys())
        undeclared = all_referenced_names - declared_names - rule_conclusion_names
        for var_name in undeclared:
            if " " not in var_name:
                errors.append(ValidationError(
                    code="UNDECLARED_REFERENCE",
                    message=f"Variable '{var_name}' is referenced but not declared as INPUT or FIXED",
                    line=None,
                    node_name=var_name,
                ))

        for var_name in declared_names:
            if var_name not in all_referenced_names:
                warnings.append(ValidationWarning(
                    code="UNUSED_DECLARATION",
                    message=f"Variable '{var_name}' is declared but never referenced in rule blocks",
                    line=declarations[var_name]["line"],
                    node_name=var_name,
                ))

    # -------------------------------------------------------------------------
    # Check 3: Import Resolution (Phase 2 Placeholder)
    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    # Check 4: DAG Cycle Check
    # -------------------------------------------------------------------------

    def _check_dag_cycles(
        self,
        parsed: Dict,
        errors: List[ValidationError],
    ) -> None:
        declarations = parsed["declarations"]
        rules = parsed["rules"]

        if not rules:
            return

        all_nodes: Set[str] = set()
        for decl_name in declarations:
            all_nodes.add(f"decl:{decl_name}")
        for rule in rules:
            all_nodes.add(f"rule:{rule['line']}")

        edges: Dict[str, Set[str]] = {n: set() for n in all_nodes}

        decl_node_map: Dict[str, str] = {
            name: f"decl:{name}" for name in declarations
        }

        rule_conclusion_map: Dict[str, List[str]] = {}
        for rule in rules:
            var_name = rule["variable_name"]
            rule_node = f"rule:{rule['line']}"
            rule_conclusion_map.setdefault(var_name, []).append(rule_node)

        for rule in rules:
            rule_node = f"rule:{rule['line']}"
            conclusion_var = rule["variable_name"]

            for ref in rule.get("references", []):
                if ref in decl_node_map:
                    edges[rule_node].add(decl_node_map[ref])
                if ref in rule_conclusion_map:
                    for dep_rule_node in rule_conclusion_map[ref]:
                        if dep_rule_node != rule_node:
                            edges[rule_node].add(dep_rule_node)

            if conclusion_var in decl_node_map:
                edges[rule_node].add(decl_node_map[conclusion_var])

        in_degree: Dict[str, int] = {n: len(edges[n]) for n in all_nodes}

        reverse: Dict[str, List[str]] = {n: [] for n in all_nodes}
        for node, deps in edges.items():
            for dep in deps:
                reverse[dep].append(node)

        queue: deque = deque(n for n in all_nodes if in_degree[n] == 0)
        visited_count = 0

        while queue:
            node = queue.popleft()
            visited_count += 1
            for dependent in reverse[node]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        if visited_count != len(all_nodes):
            cycle_nodes = [n for n in all_nodes if in_degree[n] > 0]
            var_names = []
            for cn in cycle_nodes:
                if cn.startswith("decl:"):
                    var_names.append(cn[5:])
                elif cn.startswith("rule:"):
                    line = cn[5:]
                    matching = [r for r in rules if str(r["line"]) == line]
                    var_names.append(matching[0]["variable_name"] if matching else cn)
            errors.append(ValidationError(
                code="CYCLIC_DEPENDENCY",
                message=f"Cyclic dependency detected involving: {', '.join(sorted(set(var_names))[:5])}",
                node_name=", ".join(sorted(set(var_names))[:5]),
            ))

    # -------------------------------------------------------------------------
    # Cache Management
    # -------------------------------------------------------------------------

    def _compute_content_hash(self, rule_text: str) -> str:
        return hashlib.sha256(rule_text.encode("utf-8")).hexdigest()

    def _get_cached(self, content_hash: str) -> Optional[ValidationResult]:
        if content_hash in self._cache:
            ts, result = self._cache[content_hash]
            if time.time() - ts < self._cache_ttl:
                self._cache.move_to_end(content_hash)
                return result
            del self._cache[content_hash]
        return None

    def _set_cached(self, content_hash: str, result: ValidationResult) -> None:
        if content_hash in self._cache:
            self._cache.move_to_end(content_hash)
            self._cache[content_hash] = (time.time(), result)
            return
        if len(self._cache) >= self._cache_maxsize:
            self._cache.popitem(last=False)
        self._cache[content_hash] = (time.time(), result)

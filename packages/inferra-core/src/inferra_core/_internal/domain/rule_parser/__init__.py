"""Private deterministic rule parser implementation.

Exports are resolved lazily so node modules may import syntax helpers without
creating a parser/node initialisation cycle.
"""

from importlib import import_module
from typing import Any

__all__ = [
    "DependencyTypeStringMatcher",
    "LineMatcherConstant",
    "RuleSetParser",
    "RuleSetReader",
    "RuleSetScanner",
]

_EXPORT_MODULES = {
    "DependencyTypeStringMatcher": "dependency_type_string_matcher",
    "LineMatcherConstant": "line_matcher_constant",
    "RuleSetParser": "rule_set_parser",
    "RuleSetReader": "rule_set_reader",
    "RuleSetScanner": "rule_set_scanner",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(name)
    return getattr(import_module(f"{__name__}.{module_name}"), name)

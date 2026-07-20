"""Helpers for normalising collection iteration syntax."""

import re
from typing import Optional


_QUANTIFIER_PATTERN = (
    r"NOT\s+ALL|NOT\s+NONE|AT\s+LEAST\s+\d+|AT\s+MOST\s+\d+|"
    r"EXACTLY\s+\d+|ALL|NONE|SOME"
)

_IN_ITERATE_PATTERN = re.compile(
    rf"^\s*(?P<quantifier>{_QUANTIFIER_PATTERN})\s+"
    r"(?P<alias>.+?)\s+IN\s+(?P<collection>.+?)\s*$",
    re.IGNORECASE,
)

_ITERATE_PATTERN = re.compile(
    rf"^\s*(?P<quantifier>{_QUANTIFIER_PATTERN})\s+"
    r"(?P<alias>.+?)\s+ITERATE:\s*LIST\s+OF\s+(?P<collection>.+?)\s*$",
    re.IGNORECASE,
)


def canonicalise_iterate_syntax(rule_text: str) -> str:
    """
    Convert public collection syntax to the parser's internal iterate syntax.

    Rule authors write:
        ALL item IN items

    The parser and runtime use:
        ALL item ITERATE: LIST OF items

    Keeping a single internal representation avoids duplicating iterate
    behaviour in the older tokenizer and line matcher.
    """
    parsed = parse_in_iterate(rule_text)
    if parsed is None:
        return rule_text
    quantifier, alias, collection = parsed
    return f"{quantifier} {alias} ITERATE: LIST OF {collection}"


def parse_in_iterate(rule_text: str) -> Optional[tuple[str, str, str]]:
    """Return quantifier, item alias, and collection name for an IN iterate line."""
    match = _IN_ITERATE_PATTERN.match(rule_text or "")
    if match is None:
        return None
    quantifier = normalise_quantifier(match.group("quantifier"))
    alias = match.group("alias").strip()
    collection = match.group("collection").strip()
    if not alias or not collection:
        return None
    return quantifier, alias, collection


def parse_iterate(rule_text: str) -> Optional[tuple[str, str, str]]:
    """Return quantifier, item alias, and collection name for public or internal syntax."""
    parsed = parse_in_iterate(rule_text)
    if parsed is not None:
        return parsed
    match = _ITERATE_PATTERN.match(rule_text or "")
    if match is None:
        return None
    quantifier = normalise_quantifier(match.group("quantifier"))
    alias = match.group("alias").strip()
    collection = match.group("collection").strip()
    if not alias or not collection:
        return None
    return quantifier, alias, collection


def normalise_quantifier(quantifier: str) -> str:
    """Normalise iterate quantifiers to their canonical runtime form."""
    value = re.sub(r"\s+", " ", (quantifier or "").strip()).upper()
    if value.startswith("AT LEAST "):
        return "AT LEAST " + value.rsplit(" ", 1)[1].strip()
    if value.startswith("AT MOST "):
        return "AT MOST " + value.rsplit(" ", 1)[1].strip()
    return value

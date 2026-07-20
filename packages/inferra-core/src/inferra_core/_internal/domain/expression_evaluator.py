"""Bounded parser and interpreter for INFERRA ``IS CALC`` expressions.

Rule source is untrusted data.  This module therefore implements the documented
INFERRA expression grammar directly and never delegates source text to Python or
third-party evaluation helpers.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import math
import re
from typing import Any, Mapping, Optional, Sequence, Tuple


MAX_EXPRESSION_LENGTH = 4096
MAX_EXPRESSION_TOKENS = 512
MAX_EXPRESSION_NODES = 512
MAX_EXPRESSION_DEPTH = 32
MAX_EVALUATION_STEPS = 1024
MAX_INTEGER_BITS = 4096
MAX_STRING_LENGTH = 4096
MAX_COLLECTION_LENGTH = 256
MAX_ROUND_DIGITS = 100

_ALLOWED_FUNCTIONS = frozenset({"MAX", "MIN", "ROUND"})
_SINGLE_CHARACTER_TOKENS = frozenset("+-*/(),?:<>=")
_NUMBER_PATTERN = re.compile(r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")
_MISSING = object()


class SafeExpressionError(ValueError):
    """Raised when an expression is invalid, unsupported, or exceeds limits."""


@dataclass(frozen=True)
class _Token:
    kind: str
    value: Any
    position: int


class _ExpressionNode:
    """Marker base class for the private, non-executable expression AST."""


@dataclass(frozen=True)
class _LiteralNode(_ExpressionNode):
    value: Any


@dataclass(frozen=True)
class _VariableNode(_ExpressionNode):
    name: str


@dataclass(frozen=True)
class _UnaryNode(_ExpressionNode):
    operator: str
    operand: _ExpressionNode


@dataclass(frozen=True)
class _BinaryNode(_ExpressionNode):
    operator: str
    left: _ExpressionNode
    right: _ExpressionNode


@dataclass(frozen=True)
class _ComparisonNode(_ExpressionNode):
    operator: str
    left: _ExpressionNode
    right: _ExpressionNode


@dataclass(frozen=True)
class _TernaryNode(_ExpressionNode):
    condition: _ExpressionNode
    when_true: _ExpressionNode
    when_false: _ExpressionNode


@dataclass(frozen=True)
class _CallNode(_ExpressionNode):
    function: str
    arguments: Tuple[_ExpressionNode, ...]


class _Lexer:
    def __init__(self, expression: str, variable_names: Sequence[str]) -> None:
        if not isinstance(expression, str):
            raise SafeExpressionError("Expression must be text")
        self._expression = expression
        self._length = len(expression)
        if self._length == 0 or not expression.strip():
            raise SafeExpressionError("Expression is empty")
        if self._length > MAX_EXPRESSION_LENGTH:
            raise SafeExpressionError(
                f"Expression exceeds the {MAX_EXPRESSION_LENGTH}-character limit"
            )
        self._variable_names = tuple(
            sorted(
                {str(name) for name in variable_names if str(name)},
                key=len,
                reverse=True,
            )
        )
        self._position = 0

    def tokenize(self) -> Tuple[_Token, ...]:
        tokens = []
        while self._position < self._length:
            if self._expression[self._position].isspace():
                self._position += 1
                continue

            token = (
                self._known_variable()
                or self._string_literal()
                or self._number_literal()
                or self._operator()
                or self._identifier()
            )
            if token is None:  # pragma: no cover - defensive; helpers are exhaustive
                raise SafeExpressionError(
                    f"Unsupported expression token at position {self._position}"
                )
            tokens.append(token)
            if len(tokens) > MAX_EXPRESSION_TOKENS:
                raise SafeExpressionError(
                    f"Expression exceeds the {MAX_EXPRESSION_TOKENS}-token limit"
                )

        tokens.append(_Token("EOF", None, self._length))
        return tuple(tokens)

    def _known_variable(self) -> Optional[_Token]:
        for name in self._variable_names:
            if not self._expression.startswith(name, self._position):
                continue
            end = self._position + len(name)
            if end < self._length and self._is_word_character(self._expression[end]):
                continue
            if (
                name.upper() in _ALLOWED_FUNCTIONS
                and self._next_non_space(end) == "("
            ):
                continue
            token = _Token("VARIABLE", name, self._position)
            self._position = end
            return token
        return None

    def _string_literal(self) -> Optional[_Token]:
        quote = self._expression[self._position]
        if quote not in {"'", '"'}:
            return None

        start = self._position
        self._position += 1
        characters = []
        escapes = {
            "\\": "\\",
            "'": "'",
            '"': '"',
            "n": "\n",
            "r": "\r",
            "t": "\t",
        }
        while self._position < self._length:
            character = self._expression[self._position]
            self._position += 1
            if character == quote:
                value = "".join(characters)
                if len(value) > MAX_STRING_LENGTH:
                    raise SafeExpressionError(
                        f"String literal exceeds the {MAX_STRING_LENGTH}-character limit"
                    )
                return _Token("STRING", value, start)
            if character == "\\":
                if self._position >= self._length:
                    raise SafeExpressionError("String literal ends with an escape")
                escaped = self._expression[self._position]
                self._position += 1
                if escaped not in escapes:
                    raise SafeExpressionError(
                        f"Unsupported string escape at position {self._position - 2}"
                    )
                characters.append(escapes[escaped])
                continue
            characters.append(character)
        raise SafeExpressionError(f"Unterminated string literal at position {start}")

    def _number_literal(self) -> Optional[_Token]:
        match = _NUMBER_PATTERN.match(self._expression, self._position)
        if match is None:
            return None
        raw = match.group(0)
        start = self._position
        self._position = match.end()
        digits = sum(character.isdigit() for character in raw)
        if digits > 128:
            raise SafeExpressionError("Numeric literal is too large")
        try:
            value = float(raw) if any(marker in raw for marker in ".eE") else int(raw)
        except (OverflowError, ValueError) as exc:
            raise SafeExpressionError("Invalid numeric literal") from exc
        _validate_numeric(value)
        return _Token("NUMBER", value, start)

    def _operator(self) -> Optional[_Token]:
        start = self._position
        for operator in (">=", "<="):
            if self._expression.startswith(operator, start):
                self._position += len(operator)
                return _Token(operator, operator, start)
        character = self._expression[start]
        if character not in _SINGLE_CHARACTER_TOKENS:
            return None
        self._position += 1
        return _Token(character, character, start)

    def _identifier(self) -> Optional[_Token]:
        start = self._position
        while (
            self._position < self._length
            and self._expression[self._position] not in _SINGLE_CHARACTER_TOKENS
        ):
            self._position += 1
        raw = self._expression[start:self._position].strip()
        if not raw:
            return None
        if any(
            character in raw
            for character in (
                '"',
                "\\",
                "`",
                "[",
                "]",
                "{",
                "}",
                ";",
                "!",
                "%",
                "^",
                "&",
                "|",
            )
        ):
            raise SafeExpressionError(f"Unsupported identifier at position {start}")
        if raw.startswith("_") or "__" in raw:
            raise SafeExpressionError(f"Reserved identifier at position {start}")
        return _Token("IDENTIFIER", raw, start)

    def _next_non_space(self, position: int) -> str:
        while position < self._length and self._expression[position].isspace():
            position += 1
        return self._expression[position] if position < self._length else ""

    @staticmethod
    def _is_word_character(character: str) -> bool:
        return character.isalnum() or character in {"_", "'", "’"}


class _Parser:
    def __init__(self, tokens: Sequence[_Token]) -> None:
        self._tokens = tokens
        self._position = 0
        self._node_count = 0
        self._depth = 0

    def parse(self) -> _ExpressionNode:
        result = self._parse_ternary()
        self._expect("EOF")
        return result

    def _parse_ternary(self) -> _ExpressionNode:
        condition = self._parse_comparison()
        if not self._match("?"):
            return condition
        self._enter_depth()
        try:
            when_true = self._parse_ternary()
            self._expect(":")
            when_false = self._parse_ternary()
        finally:
            self._leave_depth()
        return self._node(_TernaryNode(condition, when_true, when_false))

    def _parse_comparison(self) -> _ExpressionNode:
        left = self._parse_additive()
        if self._peek().kind not in {"=", ">", ">=", "<", "<="}:
            return left
        operator = self._advance().kind
        right = self._parse_additive()
        if self._peek().kind in {"=", ">", ">=", "<", "<="}:
            raise SafeExpressionError("Chained comparisons are not supported")
        return self._node(_ComparisonNode(operator, left, right))

    def _parse_additive(self) -> _ExpressionNode:
        result = self._parse_multiplicative()
        while self._peek().kind in {"+", "-"}:
            operator = self._advance().kind
            result = self._node(
                _BinaryNode(operator, result, self._parse_multiplicative())
            )
        return result

    def _parse_multiplicative(self) -> _ExpressionNode:
        result = self._parse_unary()
        while self._peek().kind in {"*", "/"}:
            operator = self._advance().kind
            result = self._node(_BinaryNode(operator, result, self._parse_unary()))
        return result

    def _parse_unary(self) -> _ExpressionNode:
        if self._peek().kind not in {"+", "-"}:
            return self._parse_primary()
        operator = self._advance().kind
        self._enter_depth()
        try:
            operand = self._parse_unary()
        finally:
            self._leave_depth()
        return self._node(_UnaryNode(operator, operand))

    def _parse_primary(self) -> _ExpressionNode:
        token = self._peek()
        if token.kind in {"NUMBER", "STRING"}:
            self._advance()
            return self._node(_LiteralNode(token.value))
        if token.kind == "VARIABLE":
            self._advance()
            return self._node(_VariableNode(str(token.value)))
        if token.kind == "IDENTIFIER":
            self._advance()
            if token.value == "True":
                return self._node(_LiteralNode(True))
            if token.value == "False":
                return self._node(_LiteralNode(False))
            if self._peek().kind == "(":
                return self._parse_call(str(token.value), token.position)
            return self._node(_VariableNode(str(token.value)))
        if self._match("("):
            self._enter_depth()
            try:
                result = self._parse_ternary()
                self._expect(")")
            finally:
                self._leave_depth()
            return result
        raise SafeExpressionError(
            f"Expected a value at position {token.position}"
        )

    def _parse_call(self, function: str, position: int) -> _ExpressionNode:
        if function not in _ALLOWED_FUNCTIONS:
            raise SafeExpressionError(
                f"Unsupported function '{function}' at position {position}"
            )
        self._expect("(")
        self._enter_depth()
        try:
            arguments = []
            if self._peek().kind != ")":
                while True:
                    arguments.append(self._parse_ternary())
                    if not self._match(","):
                        break
            self._expect(")")
        finally:
            self._leave_depth()
        return self._node(_CallNode(function, tuple(arguments)))

    def _node(self, node: _ExpressionNode) -> _ExpressionNode:
        self._node_count += 1
        if self._node_count > MAX_EXPRESSION_NODES:
            raise SafeExpressionError(
                f"Expression exceeds the {MAX_EXPRESSION_NODES}-node limit"
            )
        return node

    def _enter_depth(self) -> None:
        self._depth += 1
        if self._depth > MAX_EXPRESSION_DEPTH:
            raise SafeExpressionError(
                f"Expression exceeds the {MAX_EXPRESSION_DEPTH}-level nesting limit"
            )

    def _leave_depth(self) -> None:
        self._depth -= 1

    def _peek(self) -> _Token:
        return self._tokens[self._position]

    def _advance(self) -> _Token:
        token = self._peek()
        self._position += 1
        return token

    def _match(self, kind: str) -> bool:
        if self._peek().kind != kind:
            return False
        self._position += 1
        return True

    def _expect(self, kind: str) -> _Token:
        token = self._peek()
        if token.kind != kind:
            raise SafeExpressionError(
                f"Expected '{kind}' at position {token.position}"
            )
        self._position += 1
        return token


class _Interpreter:
    def __init__(self, variables: Mapping[str, Any]) -> None:
        self._variables = variables
        self._steps = 0

    def evaluate(self, node: _ExpressionNode) -> Any:
        self._steps += 1
        if self._steps > MAX_EVALUATION_STEPS:
            raise SafeExpressionError(
                f"Expression exceeds the {MAX_EVALUATION_STEPS}-step evaluation limit"
            )

        if isinstance(node, _LiteralNode):
            return _validate_value(node.value)
        if isinstance(node, _VariableNode):
            value = self._variables.get(node.name, _MISSING)
            if value is None:
                return _MISSING
            return _MISSING if value is _MISSING else _validate_value(value)
        if isinstance(node, _UnaryNode):
            value = _require_numeric(self.evaluate(node.operand))
            result = value if node.operator == "+" else -value
            return _validate_numeric(result)
        if isinstance(node, _BinaryNode):
            left = _require_numeric(self.evaluate(node.left))
            right = _require_numeric(self.evaluate(node.right))
            try:
                if node.operator == "+":
                    result = left + right
                elif node.operator == "-":
                    result = left - right
                elif node.operator == "*":
                    result = left * right
                else:
                    result = left / right
            except (ArithmeticError, TypeError) as exc:
                raise SafeExpressionError("Expression arithmetic failed") from exc
            return _validate_numeric(result)
        if isinstance(node, _ComparisonNode):
            left = self.evaluate(node.left)
            right = self.evaluate(node.right)
            if left is _MISSING or right is _MISSING:
                return False
            if node.operator == "=":
                return left == right
            comparable_left, comparable_right = _comparison_operands(left, right)
            if node.operator == ">":
                return comparable_left > comparable_right
            if node.operator == ">=":
                return comparable_left >= comparable_right
            if node.operator == "<":
                return comparable_left < comparable_right
            return comparable_left <= comparable_right
        if isinstance(node, _TernaryNode):
            condition = self.evaluate(node.condition)
            selected = node.when_true if _truthy(condition) else node.when_false
            return self.evaluate(selected)
        if isinstance(node, _CallNode):
            arguments = tuple(self.evaluate(argument) for argument in node.arguments)
            return self._call(node.function, arguments)
        raise SafeExpressionError("Unsupported expression node")  # pragma: no cover

    def _call(self, function: str, arguments: Tuple[Any, ...]) -> Any:
        if function in {"MAX", "MIN"}:
            if len(arguments) != 2:
                raise SafeExpressionError(f"{function} requires exactly two arguments")
            numeric = tuple(_require_numeric(argument) for argument in arguments)
            result = max(numeric) if function == "MAX" else min(numeric)
            return _validate_numeric(result)

        if len(arguments) not in {1, 2}:
            raise SafeExpressionError("ROUND requires one or two arguments")
        number = _require_numeric(arguments[0])
        if len(arguments) == 1:
            return _validate_numeric(round(number))
        digits = _require_numeric(arguments[1])
        if isinstance(digits, bool) or int(digits) != digits:
            raise SafeExpressionError("ROUND decimal places must be an integer")
        digits_int = int(digits)
        if abs(digits_int) > MAX_ROUND_DIGITS:
            raise SafeExpressionError(
                f"ROUND decimal places exceeds the {MAX_ROUND_DIGITS}-digit limit"
            )
        return _validate_numeric(round(number, digits_int))


def parse_expression(
    expression: str,
    variable_names: Sequence[str] = (),
) -> _ExpressionNode:
    """Parse source into a bounded, non-executable INFERRA expression AST."""
    return _Parser(_Lexer(expression, variable_names).tokenize()).parse()


def validate_expression(expression: str) -> None:
    """Validate syntax and limits without evaluating either ternary branch."""
    parse_expression(expression)


def evaluate_expression(expression: str, variables: Mapping[str, Any]) -> Any:
    """Evaluate a documented INFERRA expression using explicit variable data."""
    tree = parse_expression(expression, tuple(variables))
    result = _Interpreter(variables).evaluate(tree)
    if result is _MISSING:
        raise SafeExpressionError("Expression requires a value that is not available")
    if isinstance(result, bool):
        raise SafeExpressionError(
            "Boolean IS CALC expressions are only supported as ternary conditions"
        )
    return _validate_value(result)


def _require_numeric(value: Any) -> Any:
    if value is _MISSING:
        raise SafeExpressionError("Expression requires a value that is not available")
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise SafeExpressionError("Arithmetic operands must be numeric")
    return _validate_numeric(value)


def _validate_numeric(value: Any) -> Any:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise SafeExpressionError("Expression result is not numeric")
    if isinstance(value, int) and value.bit_length() > MAX_INTEGER_BITS:
        raise SafeExpressionError(
            f"Integer result exceeds the {MAX_INTEGER_BITS}-bit limit"
        )
    if isinstance(value, float) and not math.isfinite(value):
        raise SafeExpressionError("Floating-point result must be finite")
    if isinstance(value, Decimal) and not value.is_finite():
        raise SafeExpressionError("Decimal result must be finite")
    return value


def _validate_value(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        return _validate_numeric(value)
    if isinstance(value, str):
        if len(value) > MAX_STRING_LENGTH:
            raise SafeExpressionError(
                f"String value exceeds the {MAX_STRING_LENGTH}-character limit"
            )
        return value
    if isinstance(value, (list, tuple)):
        if len(value) > MAX_COLLECTION_LENGTH:
            raise SafeExpressionError(
                f"Collection exceeds the {MAX_COLLECTION_LENGTH}-item limit"
            )
        validated = [_validate_value(item) for item in value]
        return validated if isinstance(value, list) else tuple(validated)
    raise SafeExpressionError(
        f"Unsupported expression value type: {type(value).__name__}"
    )


def _comparison_operands(left: Any, right: Any) -> Tuple[Any, Any]:
    """Coerce numeric-looking values without losing integer/decimal precision."""
    try:
        numeric_left = Decimal(str(left))
        numeric_right = Decimal(str(right))
    except (ArithmeticError, TypeError, ValueError):
        return str(left), str(right)
    if numeric_left.is_finite() and numeric_right.is_finite():
        return numeric_left, numeric_right
    return str(left), str(right)


def _truthy(value: Any) -> bool:
    if value is _MISSING:
        return False
    return bool(value)


__all__ = [
    "MAX_EXPRESSION_DEPTH",
    "MAX_EXPRESSION_LENGTH",
    "MAX_EXPRESSION_NODES",
    "MAX_EXPRESSION_TOKENS",
    "MAX_EVALUATION_STEPS",
    "SafeExpressionError",
    "evaluate_expression",
    "parse_expression",
    "validate_expression",
]

"""Security and compatibility tests for the bounded IS CALC interpreter."""

from decimal import Decimal

import pytest

from inferra_core._internal.domain.expression_evaluator import (
    MAX_EXPRESSION_LENGTH,
    SafeExpressionError,
    evaluate_expression,
    validate_expression,
)


def test_documented_arithmetic_functions_and_natural_names() -> None:
    result = evaluate_expression(
        "MAX(Dean's base amount, minimum amount) "
        "+ MIN(ROUND(rate per day * days), cap)",
        {
            "Dean's base amount": 10,
            "minimum amount": 20,
            "rate per day": 2.4,
            "days": 2,
            "cap": 5,
        },
    )

    assert result == 25


def test_nested_ternary_and_string_comparison_are_short_circuited() -> None:
    result = evaluate_expression(
        '(category = "A" ? missing true branch : category = "B" ? 20 : 30)',
        {"category": "B"},
    )

    assert result == 20

    assert evaluate_expression(
        "large > smaller ? 1 : 0",
        {"large": 10**400, "smaller": 9 * 10**399},
    ) == 1
    assert evaluate_expression(
        "precise > rounded ? 1 : 0",
        {
            "precise": Decimal("9007199254740993"),
            "rounded": Decimal("9007199254740992"),
        },
    ) == 1


def test_missing_optional_condition_selects_fallback() -> None:
    result = evaluate_expression(
        "optional amount ? optional amount * rate : fallback amount",
        {"fallback amount": 50, "rate": 2},
    )

    assert result == 50


@pytest.mark.parametrize(
    "expression",
    (
        "__import__('builtins').sum((20, 22))",
        "open('forbidden', 'w')",
        "object.__class__",
        "(lambda: 1)()",
        "[value for value in values]",
        "base ** exponent",
        "base % divisor",
        "a != b",
        "UNKNOWN_FUNCTION(1)",
    ),
)
def test_python_and_unsupported_expression_constructs_are_rejected(
    expression: str,
) -> None:
    with pytest.raises(SafeExpressionError):
        validate_expression(expression)


def test_expression_text_cannot_create_a_file(tmp_path) -> None:
    target = tmp_path / "must-not-exist"
    expression = f"open('{target.as_posix()}', 'w')"

    with pytest.raises(SafeExpressionError):
        evaluate_expression(expression, {})

    assert not target.exists()


def test_expression_resources_and_values_are_bounded() -> None:
    with pytest.raises(SafeExpressionError, match="character limit"):
        validate_expression("1" * (MAX_EXPRESSION_LENGTH + 1))

    with pytest.raises(SafeExpressionError, match="token limit"):
        validate_expression(" + ".join(["1"] * 257))

    with pytest.raises(SafeExpressionError, match="nesting limit"):
        validate_expression("(" * 33 + "1" + ")" * 33)

    with pytest.raises(SafeExpressionError, match="Integer result"):
        evaluate_expression("large * large", {"large": 1 << 4095})

    with pytest.raises(SafeExpressionError, match="String value"):
        evaluate_expression("value", {"value": "x" * 4097})

    with pytest.raises(SafeExpressionError, match="Collection"):
        evaluate_expression("value", {"value": list(range(257))})

    with pytest.raises(SafeExpressionError, match="ROUND decimal places"):
        evaluate_expression("ROUND(value, 101)", {"value": 1.25})

    with pytest.raises(SafeExpressionError, match="finite"):
        evaluate_expression("value", {"value": float("inf")})

    with pytest.raises(SafeExpressionError, match="arithmetic failed"):
        evaluate_expression("1 / 0", {})


def test_boolean_result_is_not_a_valid_calculation_value() -> None:
    with pytest.raises(SafeExpressionError, match="Boolean IS CALC"):
        evaluate_expression("amount > threshold", {"amount": 2, "threshold": 1})

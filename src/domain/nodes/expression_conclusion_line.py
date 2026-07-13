"""
Expression Conclusion Line Module.
Handles mathematical expression evaluation in INFERRA rule sets.
Implements access levels and strong typing where appropriate.
"""

import json
import re
from datetime import datetime
from typing import Any, Dict, Optional, Tuple
from src.infrastructure.logging_config import get_logger
from src.domain.nodes.node import Node
from src.domain.nodes.line_type import LineType
from src.domain.fact_values import FactValue, FactValueType
from src.domain.tokens import Token, Tokenizer
from src.domain.nodes.meta_data import MetaData
import sympy as sp

# Protected Module-Level Logger (Access Level: Protected)
_logger = get_logger(__name__)


class ExprConclusionLine(Node):
    """
    ExprConclusionLine handles mathematical expression evaluation.
    Implements private state with public accessors.
    
    Access Levels:
    - Public: API methods for external use
    - Protected: Internal helpers (single underscore)
    - Private: Internal state (double underscore)
    """
    
    # -------------------------------------------------------------------------
    # Private Access Level: Instance Variables (Name Mangling)
    # -------------------------------------------------------------------------
    def __init__(self, id: Optional[int] = None, parent_text: Optional[str] = None, 
                 tokens: Optional[Token] = None, meta_data: Optional[MetaData] = None):
        """
        Public Constructor: Initializes ExprConclusionLine.
        
        Args:
            id: Node ID
            parent_text: Text content of the node
            tokens: Tokenized representation
            meta_data: Metadata for the node
        """
        # Private instance variable (initialized in __init__ to avoid shared state)
        self.__equation: Optional[FactValue] = None
        self.__date_formatter: str = '%Y-%m-%d'
        super().__init__(id=id, parent_text=parent_text, tokens=tokens, meta_data=meta_data)
        self._line_type = LineType.EXPR_CONCLUSION

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Getters)
    # -------------------------------------------------------------------------
    def get_equation(self) -> Optional[FactValue]:
        """
        Public API: Returns the equation.
        
        Returns:
            Equation FactValue or None
        """
        return self.__equation

    def get_line_type(self) -> LineType:
        """
        Public API: Returns the line type.
        
        Returns:
            LineType.EXPR_CONCLUSION
        """
        return LineType.EXPR_CONCLUSION

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Setters)
    # -------------------------------------------------------------------------
    def set_equation(self, equation: FactValue) -> None:
        """
        Public API: Sets the equation.
        
        Args:
            equation: Equation FactValue to set
        """
        self.__equation = equation

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Evaluation)
    # -------------------------------------------------------------------------
    def self_evaluate(self, working_memory: Dict[str, Any]) -> FactValue:
        """
        Public API: Self-evaluates the expression against working memory.
        SECURITY FIX: Removed unsafe eval(), uses constrained SymPy parsing.
        
        Args:
            working_memory: Current working memory dictionary
            
        Returns:
            FactValue result of evaluation
        """
        if self.__equation is None:
            return FactValue(None, None)
            
        equation_in_string = self.__equation.get_value()
        
        try:
            substituted = self._substitute_working_memory(equation_in_string, working_memory)
            outcome = self._evaluate_expression(substituted)
            return self._fact_value_from_outcome(outcome)
            
        except Exception as e:
            _logger.info(f'Evaluation failed: {e}. Node Name: {self.get_node_name()}')
            _logger.info(f'Now manually substitute variables in the expression: {equation_in_string}')
            
            # Fallback with safe substitution (NO eval())
            sorted_keys = sorted(working_memory, key=len, reverse=True)
            pattern_parts = [re.escape(key) for key in sorted_keys]
            pattern = r'\b(?:' + '|'.join(pattern_parts) + r')\b'
            compiled_pattern = re.compile(pattern)
            
            def replacer(match):
                key = match.group(0)
                value = working_memory[key]
                if value.get_value_type() == FactValueType.LIST:
                    value_list = {sub_value.get_value() for sub_value in value.get_value()}
                    return str(value_list)
                elif value.get_value() is None:
                    return ''
                else:
                    return str(value.get_value())
            
            substituted = compiled_pattern.sub(replacer, equation_in_string)
            substituted = ' '.join(substituted.split())
            
            # SECURITY FIX: Use constrained SymPy/ternary evaluation instead of eval()
            try:
                outcome = self._evaluate_expression(substituted)
                return self._fact_value_from_outcome(outcome)
            except Exception as e2:
                raise ValueError(f'Evaluation failed: {e2}, Node Name: {self.get_node_name()}')

    def _substitute_working_memory(self, expression: str, working_memory: Dict[str, Any]) -> str:
        substituted = expression
        for var in sorted(working_memory, key=len, reverse=True):
            value = working_memory[var]
            literal = self._fact_value_to_expression_literal(value)
            substituted = re.sub(
                r"(?<!\w)" + re.escape(var) + r"(?!\w)",
                literal,
                substituted,
            )
        return ' '.join(substituted.split())

    def _fact_value_to_expression_literal(self, value: Any) -> str:
        if isinstance(value, FactValue):
            if value.get_value_type() == FactValueType.LIST:
                items = []
                for sub_value in value.get_value():
                    item = sub_value.get_value() if isinstance(sub_value, FactValue) else sub_value
                    items.append(item)
                return repr(items)
            raw_value = value.get_value()
        else:
            raw_value = value

        if raw_value is None:
            return "0"
        if isinstance(raw_value, str):
            return repr(raw_value)
        if isinstance(raw_value, bool):
            return "True" if raw_value else "False"
        return str(raw_value)

    def _evaluate_expression(self, expression: str) -> Any:
        expression = self._strip_wrapping_parentheses(expression.strip())
        ternary = self._split_ternary(expression)
        if ternary is not None:
            condition, true_expr, false_expr = ternary
            selected = true_expr if self._evaluate_condition(condition) else false_expr
            return self._evaluate_expression(selected)

        if self._is_string_literal(expression):
            return expression[1:-1]

        local_dict = {
            "MAX": sp.Max,
            "MIN": sp.Min,
            "ROUND": round,
            "True": True,
            "False": False,
        }
        parsed = sp.parse_expr(expression, local_dict=local_dict)
        if parsed in (sp.S.true, sp.S.false):
            raise ValueError("Boolean IS CALC expressions are only supported inside ternary conditions")
        if hasattr(parsed, "evalf"):
            return parsed.evalf()
        return parsed

    def _evaluate_condition(self, expression: str) -> bool:
        expression = self._strip_wrapping_parentheses(expression.strip())
        split = self._split_top_level_comparison(expression)
        if split is None:
            return bool(self._evaluate_expression(expression))

        left_text, operator, right_text = split
        left = self._evaluate_condition_operand(left_text)
        right = self._evaluate_condition_operand(right_text)

        if operator == "=":
            return left == right
        try:
            left_number = float(left)
            right_number = float(right)
        except (TypeError, ValueError):
            left_number = str(left)
            right_number = str(right)

        if operator == ">":
            return left_number > right_number
        if operator == ">=":
            return left_number >= right_number
        if operator == "<":
            return left_number < right_number
        if operator == "<=":
            return left_number <= right_number
        raise ValueError(f"Unsupported ternary condition operator: {operator}")

    def _evaluate_condition_operand(self, expression: str) -> Any:
        expression = self._strip_wrapping_parentheses(expression.strip())
        if self._is_string_literal(expression):
            return expression[1:-1]
        result = self._evaluate_expression(expression)
        if hasattr(result, "item"):
            return result.item()
        return result

    def _fact_value_from_outcome(self, outcome: Any) -> FactValue:
        if isinstance(outcome, bool):
            return FactValue(outcome, FactValueType.BOOLEAN)
        if isinstance(outcome, str):
            return FactValue(outcome, FactValueType.STRING)

        check_tokens = Tokenizer.get_tokens(str(outcome)).get_tokens_string()
        if check_tokens == 'No':
            return FactValue(outcome, FactValueType.INTEGER)
        if check_tokens == 'De':
            return FactValue(outcome, FactValueType.DOUBLE)
        if check_tokens == 'Da':
            return FactValue(outcome, FactValueType.DATE)
        return FactValue(outcome, FactValueType.BOOLEAN)

    def _split_ternary(self, expression: str) -> Optional[Tuple[str, str, str]]:
        question_index = self._find_top_level_token(expression, "?")
        if question_index < 0:
            return None
        colon_index = self._find_top_level_token(expression, ":", start=question_index + 1)
        if colon_index < 0:
            raise ValueError("Ternary expression is missing ':'")
        return (
            expression[:question_index].strip(),
            expression[question_index + 1:colon_index].strip(),
            expression[colon_index + 1:].strip(),
        )

    def _split_top_level_comparison(self, expression: str) -> Optional[Tuple[str, str, str]]:
        operator_index, operator = self._find_top_level_comparison_operator(expression)
        if operator_index < 0:
            return None
        return (
            expression[:operator_index].strip(),
            operator,
            expression[operator_index + len(operator):].strip(),
        )

    def _find_top_level_comparison_operator(self, expression: str) -> Tuple[int, str]:
        quote = ""
        depth = 0
        i = 0
        while i < len(expression):
            ch = expression[i]
            if quote:
                if ch == quote:
                    quote = ""
                i += 1
                continue
            if ch in {"'", '"'}:
                quote = ch
                i += 1
                continue
            if ch == "(":
                depth += 1
                i += 1
                continue
            if ch == ")":
                depth -= 1
                i += 1
                continue
            if depth == 0:
                for operator in (">=", "<=", ">", "<", "="):
                    if expression.startswith(operator, i):
                        return i, operator
            i += 1
        return -1, ""

    def _find_top_level_token(self, expression: str, token: str, start: int = 0) -> int:
        quote = ""
        depth = 0
        for index in range(start, len(expression)):
            ch = expression[index]
            if quote:
                if ch == quote:
                    quote = ""
                continue
            if ch in {"'", '"'}:
                quote = ch
                continue
            if ch == "(":
                depth += 1
                continue
            if ch == ")":
                depth -= 1
                continue
            if depth == 0 and ch == token:
                return index
        return -1

    def _strip_wrapping_parentheses(self, expression: str) -> str:
        stripped = expression.strip()
        while stripped.startswith("(") and stripped.endswith(")"):
            if self._matching_outer_parentheses(stripped):
                stripped = stripped[1:-1].strip()
            else:
                break
        return stripped

    def _matching_outer_parentheses(self, expression: str) -> bool:
        quote = ""
        depth = 0
        for index, ch in enumerate(expression):
            if quote:
                if ch == quote:
                    quote = ""
                continue
            if ch in {"'", '"'}:
                quote = ch
                continue
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and index != len(expression) - 1:
                    return False
        return depth == 0

    def _is_string_literal(self, expression: str) -> bool:
        return (
            len(expression) >= 2
            and expression[0] == expression[-1]
            and expression[0] in {"'", '"'}
        )

    # -------------------------------------------------------------------------
    # Special Methods
    # -------------------------------------------------------------------------
    def __repr__(self) -> str:
        """
        Public API: String representation of the object.
        
        Returns:
            JSON string representation
        """
        return json.dumps(self.__dict__)

    # -------------------------------------------------------------------------
    # Protected Access Level: Internal Helpers (Single Underscore)
    # -------------------------------------------------------------------------
    def initialisation(self, parent_text: str, tokens: Token) -> None:
        self._initialisation(parent_text, tokens)

    def _initialisation(self, parent_text: str, tokens: Token) -> None:
        """
        Protected Helper: Initializes the expression conclusion line.
        
        Args:
            parent_text: Text content of the node
            tokens: Tokenized representation
        """
        _logger.info("Generating Expression Conclusion Line with : " + str(parent_text))

        self._node_name = parent_text
        temp_array = re.split("IS CALC ", parent_text)
        self._variable_name = temp_array[0].strip()
        index_of_c_in_tokens_string_list = tokens.get_tokens_string_list().index('C')
        self.set_value(tokens.get_tokens_string_list()[index_of_c_in_tokens_string_list].strip(),
                       re.split("IS CALC ", tokens.get_tokens_list()[index_of_c_in_tokens_string_list])[1].strip())
        self.__equation = self._value

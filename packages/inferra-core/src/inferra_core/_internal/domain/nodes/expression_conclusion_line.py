"""
Expression Conclusion Line Module.
Handles mathematical expression evaluation in INFERRA rule sets.
Implements access levels and strong typing where appropriate.
"""

import json
import re
from datetime import datetime
from typing import Any, Dict, Optional
from inferra_core._internal._logging import get_logger
from inferra_core._internal.domain.expression_evaluator import (
    SafeExpressionError,
    evaluate_expression,
)
from inferra_core._internal.domain.nodes.node import Node
from inferra_core._internal.domain.nodes.line_type import LineType
from inferra_core._internal.domain.fact_values import FactValue, FactValueType
from inferra_core._internal.domain.tokens import Token, Tokenizer
from inferra_core._internal.domain.nodes.meta_data import MetaData

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

        Rule source is parsed into an allowlisted INFERRA AST and interpreted
        without Python, SymPy, or third-party string evaluation.
        
        Args:
            working_memory: Current working memory dictionary
            
        Returns:
            FactValue result of evaluation
        """
        if self.__equation is None:
            return FactValue(None, None)

        equation_in_string = str(self.__equation.get_value())
        try:
            outcome = evaluate_expression(
                equation_in_string,
                {
                    name: self._expression_value(value)
                    for name, value in working_memory.items()
                },
            )
            return self._fact_value_from_outcome(outcome)
        except (SafeExpressionError, ArithmeticError, TypeError, ValueError) as exc:
            raise ValueError(
                f"Evaluation failed: {exc}, Node Name: {self.get_node_name()}"
            ) from exc

    def _expression_value(self, value: Any) -> Any:
        if isinstance(value, FactValue):
            if value.get_value_type() == FactValueType.LIST:
                return [self._expression_value(item) for item in value.get_value()]
            value = value.get_value()
        if value is None:
            # WANTS dependencies use a missing/unknown value as a falsey zero so
            # the documented ternary fallback can be selected deterministically.
            return 0
        if isinstance(value, tuple):
            return tuple(self._expression_value(item) for item in value)
        if isinstance(value, list):
            return [self._expression_value(item) for item in value]
        return value

    def _evaluate_expression(
        self,
        expression: str,
        variables: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Compatibility helper backed by the bounded INFERRA interpreter."""
        return evaluate_expression(expression, variables or {})

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

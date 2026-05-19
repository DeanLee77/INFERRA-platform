import json
from datetime import datetime
from typing import Any, Dict, Optional
from src.infrastructure.logging_config import get_logger
from src.domain.nodes.node import Node
from src.domain.tokens import Token
from src.domain.nodes.line_type import LineType
from src.domain.fact_values import FactValue, FactValueType

# Protected Module-Level Logger (Access Level: Protected)
_logger = get_logger(__name__)


class ComparisonLine(Node):
    """
    ComparisonLine handles comparison operations (>, <, ==, >=, <=).
    Implements private state with public accessors.
    
    Access Levels:
    - Public: API methods for external use
    - Protected: Internal helpers (single underscore)
    - Private: Internal state (double underscore)
    """
    
    # -------------------------------------------------------------------------
    # Private Access Level: Instance Variables (Name Mangling)
    # -------------------------------------------------------------------------
    def __init__(self, id: Optional[int] = None, child_text: Optional[str] = None, 
                 tokens: Optional[Token] = None):
        """
        Public Constructor: Initializes ComparisonLine.
        
        Args:
            id: Node ID
            child_text: Text content of the comparison
            tokens: Tokenized representation
        """
        # Private instance variables (initialized in __init__ to avoid shared state)
        self.__operator_string: Optional[str] = None
        self.__lhs: Optional[str] = None
        self.__rhs: Optional[FactValue] = None
        super().__init__(id=id, parent_text=child_text, tokens=tokens)
        self._line_type = LineType.COMPARISON

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Getters)
    # -------------------------------------------------------------------------
    def get_rule_name(self) -> Optional[str]:
        """
        Public API: Returns the rule name.
        
        Returns:
            Rule name string or None
        """
        return self._node_name

    def get_lhs(self) -> Optional[str]:
        """
        Public API: Returns the left-hand side of comparison.
        
        Returns:
            LHS string or None
        """
        return self.__lhs

    def get_rhs(self) -> Optional[FactValue]:
        """
        Public API: Returns the right-hand side of comparison.
        
        Returns:
            RHS FactValue or None
        """
        return self.__rhs

    def get_operator(self) -> Optional[str]:
        """
        Public API: Returns the comparison operator.
        
        Returns:
            Operator string or None
        """
        return self.__operator_string

    def get_line_type(self) -> LineType:
        """
        Public API: Returns the line type.
        
        Returns:
            LineType.COMPARISON
        """
        return LineType.COMPARISON

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Utilities)
    # -------------------------------------------------------------------------
    def get_detected_date(self, given_date_string: str) -> Optional[datetime]:
        """
        Public API: Detect the date format of a given string.
        
        Args:
            given_date_string: String to inspect for date format
            
        Returns:
            datetime object or None if no match
        """
        date_formats = [
            '%Y-%m-%d',
            '%d/%m/%Y',
            '%m/%d/%Y',
            '%d-%b-%Y',
            '%d %b %Y',
            '%Y/%m/%d',
            '%B %d, %Y',
            '%d-%m-%Y',
            '%Y.%m.%d',
            '%m-%d-%Y',
        ]
        
        date_string = given_date_string.strip()
        
        for fmt in date_formats:
            try:
                return datetime.strptime(date_string, fmt)
            except ValueError:
                continue
                
        return None

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Evaluation)
    # -------------------------------------------------------------------------
    def self_evaluate(self, working_memory: Dict[str, Any]) -> Optional[FactValue]:
        """
        Public API: Self-evaluates the comparison against working memory.
        SECURITY FIX: Removed unsafe eval(), uses safe comparison operations.
        
        Args:
            working_memory: Current working memory dictionary
            
        Returns:
            FactValue result of comparison or None
        """
        working_memory_lhs_value: Optional[FactValue] = None
        
        if self._variable_name in working_memory:
            working_memory_lhs_value = working_memory[self._variable_name]

        rhs_value_in_string = self.__rhs.get_value() if self.__rhs else None
        working_memory_rhs_value: Optional[FactValue] = None
        
        if rhs_value_in_string and rhs_value_in_string in working_memory:
            working_memory_rhs_value = working_memory[rhs_value_in_string]
        else:
            working_memory_rhs_value = self.__rhs

        if working_memory_lhs_value is None or working_memory_rhs_value is None:
            _logger.debug(
                "comparison_missing_operand",
                node_name=self.get_node_name(),
            )
            return None

        # Handle date comparison
        if ((working_memory_lhs_value is not None)
            and (working_memory_lhs_value.get_value_type() == FactValueType.DATE)) \
            or \
            ((working_memory_rhs_value is not None)
              and (working_memory_rhs_value.get_value_type() == FactValueType.DATE)):
            
            working_memory_lhs_value_str = str(working_memory_lhs_value.get_value()).split("  ")[0]
            working_memory_rhs_value_str = str(working_memory_rhs_value.get_value()).split("  ")[0]
            
            lhs_date = self.get_detected_date(working_memory_lhs_value_str)
            rhs_date = self.get_detected_date(working_memory_rhs_value_str)
            
            if lhs_date and rhs_date:
                return_value = self._compare_dates(lhs_date, rhs_date)
                return FactValue(return_value, FactValueType.BOOLEAN)
        
        # Handle numeric comparison
        elif (working_memory_lhs_value is not None) and \
             ((working_memory_lhs_value.get_value_type() == FactValueType.DECIMAL)
                or (working_memory_lhs_value.get_value_type() == FactValueType.DOUBLE)
                or (working_memory_lhs_value.get_value_type() == FactValueType.INTEGER)):
            
            return_value = self._compare_numeric(
                working_memory_lhs_value.get_value(),
                working_memory_rhs_value.get_value()
            )
            return FactValue(return_value, FactValueType.BOOLEAN)
        
        # Handle list comparison
        elif working_memory_lhs_value is not None and \
             working_memory_lhs_value.get_value_type() == FactValueType.LIST:
            
            for fact_value_in_list in working_memory_lhs_value.get_value():
                if fact_value_in_list.get_value() == working_memory_rhs_value.get_value():
                    return FactValue(True, FactValueType.BOOLEAN)
            return FactValue(False, FactValueType.BOOLEAN)
        
        # Handle string comparison
        else:
            working_memory_rhs_value_str = " "
            if working_memory_rhs_value.get_value_type() == FactValueType.DEFI_STRING:
                # SECURITY FIX: Safe string handling without eval()
                working_memory_rhs_value_str = str(working_memory_rhs_value.get_value())
            else:
                working_memory_rhs_value_str = str(working_memory_rhs_value.get_value())
            
            return_value = self._compare_strings(
                str(working_memory_lhs_value.get_value()),
                working_memory_rhs_value_str
            )
            return FactValue(return_value, FactValueType.BOOLEAN)

    # -------------------------------------------------------------------------
    # Protected Access Level: Internal Helpers (Single Underscore)
    # -------------------------------------------------------------------------
    def _compare_dates(self, lhs_date: datetime, rhs_date: datetime) -> bool:
        """
        Protected Helper: Compares two date objects.
        
        Args:
            lhs_date: Left-hand side date
            rhs_date: Right-hand side date
            
        Returns:
            Boolean result of comparison
        """
        if self.__operator_string == ">":
            return lhs_date > rhs_date
        elif self.__operator_string == ">=":
            return lhs_date >= rhs_date
        elif self.__operator_string == "<":
            return lhs_date < rhs_date
        elif self.__operator_string == "<=":
            return lhs_date <= rhs_date
        elif self.__operator_string == "==":
            return lhs_date == rhs_date
        return False

    def _compare_numeric(self, lhs: Any, rhs: Any) -> bool:
        """
        Protected Helper: Compares two numeric values.
        
        Args:
            lhs: Left-hand side value
            rhs: Right-hand side value
            
        Returns:
            Boolean result of comparison
        """
        if self.__operator_string == ">":
            return lhs > rhs
        elif self.__operator_string == ">=":
            return lhs >= rhs
        elif self.__operator_string == "<":
            return lhs < rhs
        elif self.__operator_string == "<=":
            return lhs <= rhs
        elif self.__operator_string == "==":
            return lhs == rhs
        return False

    def _compare_strings(self, lhs: str, rhs: str) -> bool:
        """
        Protected Helper: Compares two string values.
        
        Args:
            lhs: Left-hand side string
            rhs: Right-hand side string
            
        Returns:
            Boolean result of comparison
        """
        if self.__operator_string == ">":
            return lhs > rhs
        elif self.__operator_string == ">=":
            return lhs >= rhs
        elif self.__operator_string == "<":
            return lhs < rhs
        elif self.__operator_string == "<=":
            return lhs <= rhs
        elif self.__operator_string == "==":
            return lhs == rhs
        return False

    # -------------------------------------------------------------------------
    # Protected Access Level: Initialization (Single Underscore)
    # -------------------------------------------------------------------------
    def initialisation(self, child_text: str, tokens: Token) -> None:
        self._initialisation(child_text, tokens)

    def _initialisation(self, child_text: str, tokens: Token) -> None:
        """
        Protected Helper: Initializes the comparison line with text and tokens.
        
        Args:
            child_text: Text content of the comparison
            tokens: Tokenized representation
        """
        _logger.info("Generating Comparison Line with : " + str(child_text))

        self._node_name = child_text
        
        # In 'eval' engine '=' operator means assigning a value,
        # hence if the operator is '=' then it needs to be replaced with '=='.
        operator_index = tokens.get_tokens_string_list().index("O")
        if tokens.get_tokens_list()[operator_index] == "=":
            self.__operator_string = "=="
            self._variable_name = child_text.split("=")[0].strip()
        else:
            self.__operator_string = tokens.get_tokens_list()[operator_index]
            self._variable_name = child_text.split(self.__operator_string)[0].strip()

        self.__lhs = self._variable_name
        tokens_string_list_size = len(tokens.get_tokens_string_list())
        last_token = tokens.get_tokens_list()[tokens_string_list_size - 1]
        last_token_string = tokens.get_tokens_string_list()[tokens_string_list_size - 1]
        self.set_value(last_token_string, last_token)
        self.__rhs = self._value

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

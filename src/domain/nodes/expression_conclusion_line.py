"""
Expression Conclusion Line Module.
Handles mathematical expression evaluation in INFERRA rule sets.
Implements access levels and strong typing where appropriate.
"""

import json
import re
from datetime import datetime
from typing import Any, Dict, Optional
from src.shared.loggers import Logger
from src.domain.nodes.node import Node
from src.domain.nodes.line_type import LineType
from src.domain.fact_values import FactValue, FactValueType
from src.domain.tokens import Token, Tokenizer
from src.domain.nodes.meta_data import MetaData
import sympy as sp

# Protected Module-Level Logger (Access Level: Protected)
_logger: Logger = Logger.get_logger(__name__)


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
        super().__init__(id=id, parent_text=parent_text, tokens=tokens, meta_data=meta_data)
        self._line_type = LineType.EXPR_CONCLUSION
        # Private instance variable (initialized in __init__ to avoid shared state)
        self.__equation: Optional[FactValue] = None
        self.__date_formatter: str = '%Y-%m-%d'

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
        SECURITY FIX: Removed unsafe eval(), uses SymPy for safe evaluation.
        
        Args:
            working_memory: Current working memory dictionary
            
        Returns:
            FactValue result of evaluation
        """
        if self.__equation is None:
            return FactValue(None, None)
            
        equation_in_string = self.__equation.get_value()
        
        try:
            # Safe evaluation using SymPy
            symbols = {}
            substituted = equation_in_string
            
            for i, (var, value) in enumerate(working_memory.items()):
                symbol_name = f'v{i}'
                symbols[symbol_name] = value
                substituted = substituted.replace(var, symbol_name)
            
            substituted = ' '.join(substituted.split())
            expression = sp.parse_expr(substituted)

            subs_dict = {}
            for symbol_name, value in symbols.items():
                if value.get_value_type() == FactValueType.LIST:
                    value_list = {sub_value.get_value() for sub_value in value.get_value()}
                    subs_dict[symbol_name] = value_list
                elif value.get_value() is None:
                    subs_dict[symbol_name] = ''
                else:
                    subs_dict[symbol_name] = value.get_value()
            
            result = expression.subs(subs_dict)
            outcome = result.evalf()
            check_tokens = Tokenizer.get_tokens(str(outcome)).get_tokens_string()

            if check_tokens == 'No':
                return_value = FactValue(outcome, FactValueType.INTEGER)
            elif check_tokens == 'De':
                return_value = FactValue(outcome, FactValueType.DOUBLE)
            elif check_tokens == 'Da':
                return_value = FactValue(outcome, FactValueType.DATE)
            else:
                return_value = FactValue(outcome, FactValueType.BOOLEAN)

            return return_value
            
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
            
            # SECURITY FIX: Use SymPy instead of eval()
            try:
                expression = sp.parse_expr(substituted)
                outcome = expression.evalf()
                
                check_tokens = Tokenizer.get_tokens(str(outcome)).get_tokens_string()
                if check_tokens == 'No':
                    return_value = FactValue(outcome, FactValueType.INTEGER)
                elif check_tokens == 'De':
                    return_value = FactValue(outcome, FactValueType.DOUBLE)
                elif check_tokens == 'Da':
                    return_value = FactValue(outcome, FactValueType.DATE)
                else:
                    return_value = FactValue(outcome, FactValueType.BOOLEAN)
                
                return return_value
            except Exception as e2:
                raise ValueError(f'Evaluation failed: {e2}, Node Name: {self.get_node_name()}')

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

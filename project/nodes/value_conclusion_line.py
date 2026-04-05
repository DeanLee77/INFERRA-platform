"""
Value Conclusion Line Module.
Represents value conclusion nodes in PALOS rule sets.
Implements access levels and strong typing where appropriate.
"""

import json
from typing import Any, Dict, Optional
from project.loggers import Logger
from project.nodes.node import Node
from project.nodes.line_type import LineType
from project.fact_values import FactValue
from project.tokens import Token
from project.nodes.meta_data import MetaData

# Protected Module-Level Logger (Access Level: Protected)
_logger: Logger = Logger.get_logger(__name__)


class ValueConclusionLine(Node):
    """
    ValueConclusionLine represents rules in formats:
    1. 'A-statement IS B-statement'
    2. 'A-item name IS IN LIST: B-list name'
    3. 'A-statement' (plain statement)
    
    Access Levels:
    - Public: API methods for external use
    - Protected: Internal helpers (single underscore)
    - Private: Internal state (double underscore)
    """
    
    # -------------------------------------------------------------------------
    # Private Access Level: Instance Variables (Name Mangling)
    # -------------------------------------------------------------------------
    def __init__(
        self,
        id: Optional[int] = None,
        node_text: Optional[str] = None,
        tokens: Optional[Token] = None,
        meta_data: Optional[MetaData] = None,
    ):
        """
        Public Constructor: Initializes ValueConclusionLine.
        
        Args:
            id: Node ID
            node_text: Text content of the node
            tokens: Tokenized representation
            meta_data: Metadata for the node
        """
        super().__init__(id=id, parent_text=node_text, tokens=tokens, meta_data=meta_data)
        self._line_type = LineType.VALUE_CONCLUSION
        # Private instance variable (initialized in __init__ to avoid shared state)
        self.__is_plain_statement_format: bool = False

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods
    # -------------------------------------------------------------------------
    def __repr__(self) -> str:
        """
        Public API: String representation of the node.
        
        Returns:
            JSON string representation
        """
        return json.dumps(self.__dict__)

    def initialisation(self, node_text: str, tokens: Token) -> None:
        """
        Public API: Initializes the line with text and tokens.
        
        Args:
            node_text: Text content of the node
            tokens: Tokenized representation
        """
        _logger.info("Generating ValueConclusion Line with : " + str(node_text))

        token_string_list_size = len(tokens.get_tokens_string_list())
        self.__is_plain_statement_format = len(list(filter(lambda c: 'IS' in c, tokens.get_tokens_list()))) == 0

        if not self.__is_plain_statement_format:
            self._variable_name = node_text[:node_text.index(' IS')].strip()
            last_token = tokens.get_tokens_list()[token_string_list_size - 1]
        else:
            self._variable_name = node_text
            last_token = 'False'
        
        self._node_name = node_text
        last_token_string = tokens.get_tokens_string_list()[token_string_list_size - 1]
        self._set_value(last_token_string, last_token)

    def get_is_plain_statement(self) -> bool:
        """
        Public API: Checks if line is plain statement format.
        
        Returns:
            True if plain statement format
        """
        return self.__is_plain_statement_format

    def get_line_type(self) -> LineType:
        """
        Public API: Returns the line type.
        
        Returns:
            LineType.VALUE_CONCLUSION
        """
        return LineType.VALUE_CONCLUSION

    def self_evaluate(self, working_memory: Dict[str, Any]) -> Optional[FactValue]:
        """
        Public API: Self-evaluates the node against working memory.
        
        Args:
            working_memory: Current working memory dictionary
            
        Returns:
            FactValue result or None
        """
        fv: Optional[FactValue] = None
        if not self.__is_plain_statement_format:
            if len(list(filter(lambda c: c == 'IS', list(self._tokens.get_tokens_list())))) > 0:
                fv = self._value
            elif len(list(filter(lambda c: c.find('IS IN LIST') != -1, list(self._tokens.get_tokens_list())))) > 0:
                line_value = False
                list_name = self.get_fact_value().get_value()
                if working_memory.get(list_name) is not None:
                    variable_value_from_working_memory = working_memory.get(self._variable_name)
                    if variable_value_from_working_memory is not None:
                        line_value = len(list(filter(
                            lambda fact_value: fact_value.get_value() == variable_value_from_working_memory.get_value(),
                            working_memory[list_name].get_value()
                        ))) > 0
                    else:
                        line_value = len(list(filter(
                            lambda fact_value: self._variable_name == fact_value.get_value(),
                            working_memory[list_name].get_value()
                        ))) > 0
                fv = FactValue(line_value)
        return fv
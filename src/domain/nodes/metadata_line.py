"""
Metadata Line Module.
Handles metadata lines (INPUT, FIXED, etc.) in INFERRA rule sets.
Implements access levels and strong typing where appropriate.
"""

import re
from typing import Optional
from datetime import datetime
from src.infrastructure.logging_config import get_logger
from src.domain.fact_values import FactValue, FactValueType
from src.domain.nodes.line_type import LineType
from src.domain.nodes.meta_type import MetaType
from .node import Node
from src.domain.tokens import Token

# Protected Module-Level Logger (Access Level: Protected)
_logger = get_logger(__name__)


class MetadataLine(Node):
    """
    MetadataLine represents INPUT and FIXED metadata declarations.
    Implements private state with public accessors.
    
    Access Levels:
    - Public: API methods for external use
    - Protected: Internal helpers (single underscore)
    - Private: Internal state (double underscore)
    """
    
    # -------------------------------------------------------------------------
    # Private Access Level: Instance Variables (Name Mangling)
    # -------------------------------------------------------------------------
    def __init__(self, node_text: str, tokens: Token):
        """
        Public Constructor: Initializes MetadataLine.
        
        Args:
            node_text: Text content of the metadata line
            tokens: Tokenized representation
        """
        # Private instance variables (initialized in __init__ to avoid shared state)
        self.__meta_type: Optional[MetaType] = None
        self.__name: Optional[str] = None
        super().__init__(parent_text=node_text, tokens=tokens)
        self._line_type = LineType.META

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods
    # -------------------------------------------------------------------------
    def initialisation(self, parent_text: str, tokens: Token) -> None:
        """
        Public API: Initializes the metadata line with text and tokens.
        
        Args:
            parent_text: Text content of the metadata line
            tokens: Tokenized representation
        """
        _logger.info("Generating Metadata Line with : " + str(parent_text))
        self.__name = parent_text
        self._node_name = parent_text
        self._set_meta_type(parent_text)

        if self.__meta_type == MetaType.FIXED:
            pattern = re.compile(r"^FIXED\s+(.+?)\s+(IS|AS)\s+(.+)$")
            match = pattern.match(parent_text)

            if match:
                self._set_value(f"{match.group(2)} {match.group(3)}", tokens)
                self._variable_name = match.group(1).strip()
        
        if self.__meta_type == MetaType.INPUT:
            pattern = re.compile(r"^INPUT\s+(.+?)\s+AS\s+(.+)$")
            match = pattern.match(parent_text)

            if match:
                self._set_value(match.group(2).strip(), tokens)
                self._variable_name = match.group(1).strip()

    def _set_value(self, value_in_string: str, tokens: Token) -> None:
        """
        Protected Helper: Sets the value based on token analysis.
        
        Args:
            value_in_string: Value string to parse
            tokens: Tokenized representation
        """
        token_string_list_size = len(tokens.get_tokens_string_list())
        last_token_string = tokens.get_tokens_string_list()[token_string_list_size - 1]
        temp_array = re.split(' ', value_in_string)
        temp_str = temp_array[0]

        if self.__meta_type == MetaType.FIXED:
            if temp_str == "IS":
                if Node.is_date(last_token_string):
                    self._value = FactValue(datetime.strptime(temp_array[1], '%d/%m/%Y').strftime('%d/%m/%Y'), FactValueType.DATE)
                elif Node.is_double(last_token_string):
                    self._value = FactValue(float(temp_array[1]), FactValueType.DOUBLE)
                elif Node.is_integer(last_token_string):
                    self._value = FactValue(int(temp_array[1]), FactValueType.INTEGER)
                elif Node.is_boolean(last_token_string):
                    if temp_array[1].lower() == 'false':
                        self._value = FactValue(False, FactValueType.BOOLEAN)
                    else:
                        self._value = FactValue(True, FactValueType.BOOLEAN)
                elif Node.is_hash(last_token_string):
                    self._value = FactValue(temp_array[1], FactValueType.HASH)
                elif Node.is_url(last_token_string):
                    self._value = FactValue(temp_array[1], FactValueType.URL)
                elif Node.is_guid(last_token_string):
                    self._value = FactValue(temp_array[1], FactValueType.GUID)
            elif temp_str == 'AS':
                if temp_array[1] == 'LIST':
                    self._value = FactValue(list(), FactValueType.LIST)
                else:
                    self._value = FactValue('WARNING', FactValueType.WARNING)
        elif self.__meta_type == MetaType.INPUT:
            if len(temp_array) > 1:
                temp_str_2 = temp_array[2]
                if FactValueType.LIST.value == temp_str:
                    value_list = list()
                    if Node.is_date(last_token_string):
                        temp_value = FactValue(datetime.strptime(temp_str_2, '%d/%m/%Y').strftime("%d/%m/%Y"), FactValueType.DATE)
                    elif Node.is_double(last_token_string):
                        temp_value = FactValue(float(temp_str_2), FactValueType.DOUBLE)
                    elif Node.is_integer(last_token_string):
                        temp_value = FactValue(int(temp_str_2), FactValueType.INTEGER)
                    elif Node.is_hash(last_token_string):
                        temp_value = FactValue(temp_str_2, FactValueType.HASH)
                    elif Node.is_url(last_token_string):
                        temp_value = FactValue(temp_str_2, FactValueType.URL)
                    elif Node.is_guid(last_token_string):
                        temp_value = FactValue(temp_str_2, FactValueType.GUID)
                    elif Node.is_boolean(last_token_string):
                        if temp_str_2.lower() == 'false':
                            temp_value = FactValue(False, FactValueType.BOOLEAN)
                        else:
                            temp_value = FactValue(True, FactValueType.BOOLEAN)
                    else:
                        temp_value = FactValue(temp_str_2, FactValueType.STRING)
                    value_list.append(temp_value)
                    self._value = FactValue(value_list, FactValueType.LIST)
                    self._value.set_default_value(temp_value)
                elif FactValueType.TEXT.value == temp_str or FactValueType.STRING.value == temp_str:
                    self._value = FactValue(temp_str_2, FactValueType.STRING)
                elif FactValueType.DATE.value == temp_str:
                    self._value = FactValue(datetime.strptime(temp_str_2, '%d/%m/%Y').strftime("%d/%m/%Y"), FactValueType.DATE)
                elif FactValueType.INTEGER.value == temp_str:
                    self._value = FactValue(int(temp_str_2), FactValueType.INTEGER)
                elif temp_str == "NUMBER" or FactValueType.DOUBLE.value == temp_str:
                    self._value = FactValue(float(temp_str_2), FactValueType.DOUBLE)
                elif FactValueType.DECIMAL.value == temp_str:
                    self._value = FactValue(float(temp_str_2), FactValueType.DOUBLE)
                elif FactValueType.BOOLEAN.value == temp_str:
                    if temp_str_2.lower() == 'true':
                        value = True
                    else:
                        value = False
                    self._value = FactValue(value, FactValueType.BOOLEAN)
                elif FactValueType.URL.value == temp_str:
                    self._value = FactValue(temp_str_2, FactValueType.URL)
                elif FactValueType.HASH.value == temp_str:
                    self._value = FactValue(temp_str_2, FactValueType.HASH)
                elif FactValueType.GUID.value == temp_str:
                    self._value = FactValue(temp_str_2, FactValueType.GUID)
            else:
                if FactValueType.LIST.value == temp_str:
                    self._value = FactValue(list(), FactValueType.LIST)
                elif FactValueType.TEXT.value == temp_str or FactValueType.STRING.value == temp_str:
                    self._value = FactValue(None, FactValueType.STRING)
                elif FactValueType.URL.value == temp_str:
                    self._value = FactValue(None, FactValueType.URL)
                elif FactValueType.HASH.value == temp_str:
                    self._value = FactValue(None, FactValueType.HASH)
                elif FactValueType.GUID.value == temp_str:
                    self._value = FactValue(None, FactValueType.GUID)
                elif FactValueType.DATE.value == temp_str:
                    self._value = FactValue(None, FactValueType.DATE)
                elif FactValueType.INTEGER.value == temp_str:
                    self._value = FactValue(None, FactValueType.INTEGER)
                elif temp_str == "NUMBER" or FactValueType.DOUBLE.value == temp_str:
                    self._value = FactValue(None, FactValueType.DOUBLE)
                elif FactValueType.DECIMAL.value == temp_str:
                    self._value = FactValue(None, FactValueType.DOUBLE)
                elif FactValueType.BOOLEAN.value == temp_str:
                    self._value = FactValue(None, FactValueType.BOOLEAN)

    def _set_meta_type(self, parent_text: str) -> None:
        """
        Protected Helper: Sets the meta type based on parent text.
        
        Args:
            parent_text: Text to analyze for meta type
        """
        self.__meta_type = None
        for x in MetaType.get_all_meta_type():
            if x.value in parent_text:
                self.__meta_type = x
                break

    def get_meta_type(self) -> Optional[MetaType]:
        """
        Public API: Returns the meta type.
        
        Returns:
            MetaType or None
        """
        return self.__meta_type

    def get_name(self) -> Optional[str]:
        """
        Public API: Returns the name.
        
        Returns:
            Name string or None
        """
        return self.__name

    def get_line_type(self) -> LineType:
        """
        Public API: Returns the line type.
        
        Returns:
            LineType.META
        """
        return LineType.META

    def self_evaluate(self, working_memory: dict) -> FactValue:
        """
        Public API: Self-evaluates the node (metadata lines don't evaluate).
        
        Args:
            working_memory: Current working memory dictionary
            
        Returns:
            FactValue(None, None)
        """
        return FactValue(None, None)

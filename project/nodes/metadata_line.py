"""
Metadata Line Module.
Handles metadata lines (INPUT, FIXED, etc.) in PALOS rule sets.
Implements access levels and strong typing where appropriate.
"""

import re
from typing import Optional
from datetime import datetime
from project.loggers import Logger
from project.fact_values import FactValue, FactValueType
from . import LineType, MetaType
from .node import Node
from project.tokens import Token

# Protected Module-Level Logger (Access Level: Protected)
_logger: Logger = Logger.get_logger(__name__)


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
        super().__init__(parent_text=node_text, tokens=tokens)
        self._line_type = LineType.META
        # Private instance variables (initialized in __init__ to avoid shared state)
        self.__meta_type: Optional[MetaType] = None
        self.__name: Optional[str] = None

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
            pattern = re.compile(r"^(FIXED)(.*)(\s[AS|IS]\s*.*)")
            match = pattern.match(parent_text)

            if match:
                self._set_value(match.group(3).strip(), tokens)
                self._variable_name = match.group(2).strip()
        
        if self.__meta_type == MetaType.INPUT:
            pattern = re.compile(r"^(INPUT)(.*)(AS)(.*)[(IS)(.*)]?")
            match = pattern.match(parent_text)

            if match:
                self._set_value(match.group(4).strip(), tokens)
                self._variable_name = match.group(2).strip()

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
                if self._is_date(last_token_string):
                    self._value = FactValue(datetime.strptime(temp_array[1], '%d/%m/%Y').strftime('%d/%m/%Y'), FactValueType.DATE)
                elif self._is_double(last_token_string):
                    self._value = FactValue(float(temp_array[1]), FactValueType.DOUBLE)
                elif self._is_integer(last_token_string):
                    self._value = FactValue(int(temp_array[1]), FactValueType.INTEGER)
                elif self._is_boolean(last_token_string):
                    if temp_array[1].lower() == 'false':
                        self._value = FactValue(False, FactValueType.BOOLEAN)
                    else:
                        self._value = FactValue(True, FactValueType.BOOLEAN)
                elif self._is_hash(last_token_string):
                    self._value = FactValue(temp_array[1], FactValueType.HASH)
                elif self._is_url(last_token_string):
                    self._value = FactValue(temp_array[1], FactValueType.URL)
                elif self._is_guid(last_token_string):
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
                    if Node._is_date(last_token_string):
                        temp_value = FactValue(datetime.strptime(temp_str_2, '%d/%m/%Y').strftime("%d/%m/%Y"), FactValueType.DATE)
                    elif Node._is_double(last_token_string):
                        temp_value = FactValue(float(temp_str_2), FactValueType.DOUBLE)
                    elif Node._is_integer(last_token_string):
                        temp_value = FactValue(int(temp_str_2), FactValueType.INTEGER)
                    elif Node._is_hash(last_token_string):
                        temp_value = FactValue(temp_str_2, FactValueType.HASH)
                    elif Node._is_url(last_token_string):
                        temp_value = FactValue(temp_str_2, FactValueType.URL)
                    elif Node._is_guid(last_token_string):
                        temp_value = FactValue(temp_str_2, FactValueType.GUID)
                    elif Node._is_boolean(last_token_string):
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
                elif FactValueType.NUMBER.value == temp_str or FactValueType.INTEGER.value == temp_str:
                    self._value = FactValue(int(temp_str_2), FactValueType.INTEGER)
                elif FactValueType.DECIMAL.value == temp_str or FactValueType.DOUBLE.value == temp_str:
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
                elif FactValueType.NUMBER.value == temp_str or FactValueType.INTEGER.value == temp_str:
                    self._value = FactValue(None, FactValueType.INTEGER)
                elif FactValueType.DECIMAL.value == temp_str or FactValueType.DOUBLE.value == temp_str:
                    self._value = FactValue(None, FactValueType.DOUBLE)
                elif FactValueType.BOOLEAN.value == temp_str:
                    self._value = FactValue(None, FactValueType.BOOLEAN)

    def _set_meta_type(self, parent_text: str) -> None:
        """
        Protected Helper: Sets the meta type based on parent text.
        
        Args:
            parent_text: Text to analyze for meta type
        """
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
"""
Node Base Class.
Abstract base class for all rule nodes in PALOS analysis.
Implements access levels and strong typing where appropriate.
"""

import json
import re
import abc
from abc import ABCMeta
from typing import Any, Optional
from project.fact_values import FactValueType
from project.nodes.line_type import LineType
from project.tokens import Token, TokenStringDictionary
from project.fact_values import FactValue
from project.nodes.meta_data import MetaData
from project.loggers import Logger

# Protected Module-Level Logger (Access Level: Protected)
_logger: Logger = Logger.get_logger(__name__)


class Node(metaclass=ABCMeta):
    """
    Abstract base class for all rule nodes.
    Implements private state with public accessors.
    
    Access Levels:
    - Public: API methods for external use
    - Protected: Internal helpers (single underscore)
    - Private: Internal state (double underscore)
    """
    
    # -------------------------------------------------------------------------
    # Private Access Level: Class Variables (Name Mangling)
    # -------------------------------------------------------------------------
    __static_node_id: int = 0

    # -------------------------------------------------------------------------
    # Protected Access Level: Instance Variables (Single Underscore)
    # -------------------------------------------------------------------------
    def __init__(
        self,
        id: Optional[int] = None,
        parent_text: Optional[str] = None,
        tokens: Optional[Token] = None,
        meta_data: Optional[MetaData] = None,
    ):
        """
        Public Constructor: Initializes Node.
        
        Args:
            id: Node ID
            parent_text: Text content of the node
            tokens: Tokenized representation
            meta_data: Metadata for the node
        """
        # Protected instance variables (initialized in __init__)
        self._node_unique_id: int = Node.__static_node_id
        self._node_id: Optional[int] = id
        self._node_name: Optional[str] = None
        self._node_line: Optional[int] = None
        self._variable_name: Optional[str] = None
        self._value: FactValue = FactValue()
        self._tokens: Token = Token()
        self._line_type: Optional[LineType] = None
        self._meta_data: Optional[MetaData] = None
        
        Node.__static_node_id += 1
        
        if parent_text is not None and tokens is not None:
            self.initialisation(parent_text, tokens)
            self._tokens = tokens
        
        if meta_data is not None:
            self._meta_data = meta_data

    # -------------------------------------------------------------------------
    # Public Access Level: Abstract Methods
    # -------------------------------------------------------------------------
    @abc.abstractmethod
    def initialisation(self, parent_text: str, tokens: Token) -> None:
        """
        Public API: Initializes the node with text and tokens.
        
        Args:
            parent_text: Text content of the node
            tokens: Tokenized representation
        """
        pass

    @abc.abstractmethod
    def get_line_type(self) -> LineType:
        """
        Public API: Returns the line type.
        
        Returns:
            LineType of the node
        """
        pass

    @abc.abstractmethod
    def self_evaluate(self, working_memory: dict) -> FactValue:
        """
        Public API: Self-evaluates the node against working memory.
        
        Args:
            working_memory: Current working memory dictionary
            
        Returns:
            FactValue result
        """
        pass

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Getters)
    # -------------------------------------------------------------------------
    def get_meta_data(self) -> Optional[MetaData]:
        """
        Public API: Returns the metadata.
        
        Returns:
            MetaData object or None
        """
        return self._meta_data

    def get_node_line(self) -> Optional[int]:
        """
        Public API: Returns the node line number.
        
        Returns:
            Line number or None
        """
        return self._node_line

    def get_node_id(self) -> Optional[int]:
        """
        Public API: Returns the node ID.
        
        Returns:
            Node ID or None
        """
        return self._node_id

    def get_node_name(self) -> Optional[str]:
        """
        Public API: Returns the node name.
        
        Returns:
            Node name or None
        """
        return self._node_name

    def get_tokens(self) -> Token:
        """
        Public API: Returns the tokens.
        
        Returns:
            Token object
        """
        return self._tokens

    def get_variable_name(self) -> Optional[str]:
        """
        Public API: Returns the variable name.
        
        Returns:
            Variable name or None
        """
        return self._variable_name

    def get_fact_value(self) -> FactValue:
        """
        Public API: Returns the fact value.
        
        Returns:
            FactValue object
        """
        return self._value

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Setters)
    # -------------------------------------------------------------------------
    def set_meta_data(self, meta_data: MetaData) -> None:
        """
        Public API: Sets the metadata.
        
        Args:
            meta_data: MetaData to set
        """
        self._meta_data = meta_data

    def set_node_line(self, node_line: int) -> None:
        """
        Public API: Sets the node line number.
        
        Args:
            node_line: Line number to set
        """
        self._node_line = node_line

    def set_node_variable(self, new_variable_name: str) -> None:
        """
        Public API: Sets the variable name.
        
        Args:
            new_variable_name: New variable name
        """
        self._variable_name = new_variable_name

    def set_value(self, last_token_string: Any, last_token: Any = None) -> None:
        """
        Public API: Sets the fact value.
        
        Args:
            last_token_string: Token string
            last_token: Token object (optional)
        """
        if last_token is None:
            self._value = last_token_string
        else:
            if re.match(r"Q", last_token_string, re.IGNORECASE):
                self._value = FactValue(last_token, FactValueType.DEFI_STRING)
            elif not re.match(r"[CLMU]", last_token_string, re.IGNORECASE):
                self._value = FactValue(last_token, TokenStringDictionary.find_fact_value_type(last_token_string))
            else:
                if Node.is_boolean(last_token):
                    if re.match(r"false", last_token, re.IGNORECASE):
                        self._value = FactValue(False, FactValueType.BOOLEAN)
                    elif re.match(r"true", last_token, re.IGNORECASE):
                        self._value = FactValue(True, FactValueType.BOOLEAN)
                elif re.match(r"(^[\'\"])(.*)([\'\"]$)", last_token, re.IGNORECASE):
                    self._value = FactValue(last_token, FactValueType.DEFI_STRING)
                else:
                    self._value = FactValue(last_token, TokenStringDictionary.find_fact_value_type(last_token_string))

    # -------------------------------------------------------------------------
    # Public Access Level: Static Methods
    # -------------------------------------------------------------------------
    @staticmethod
    def is_boolean(in_string: str) -> bool:
        """
        Public API: Checks if string represents a boolean.
        
        Args:
            in_string: String to check
            
        Returns:
            True if boolean, False otherwise
        """
        if re.match(r"false+", in_string, re.IGNORECASE) or re.match(r"true+", in_string, re.IGNORECASE):
            return True
        return False

    @staticmethod
    def is_integer(in_string: str) -> bool:
        """
        Public API: Checks if string represents an integer.
        
        Args:
            in_string: String to check
            
        Returns:
            True if integer, False otherwise
        """
        return "No" == in_string

    @staticmethod
    def is_double(in_string: str) -> bool:
        """
        Public API: Checks if string represents a double.
        
        Args:
            in_string: String to check
            
        Returns:
            True if double, False otherwise
        """
        return "De" == in_string

    @staticmethod
    def is_date(in_string: str) -> bool:
        """
        Public API: Checks if string represents a date.
        
        Args:
            in_string: String to check
            
        Returns:
            True if date, False otherwise
        """
        return "Da" == in_string

    @staticmethod
    def is_url(in_string: str) -> bool:
        """
        Public API: Checks if string represents a URL.
        
        Args:
            in_string: String to check
            
        Returns:
            True if URL, False otherwise
        """
        return "Url" == in_string

    @staticmethod
    def is_hash(in_string: str) -> bool:
        """
        Public API: Checks if string represents a hash.
        
        Args:
            in_string: String to check
            
        Returns:
            True if hash, False otherwise
        """
        return "Ha" == in_string

    @staticmethod
    def is_guid(in_string: str) -> bool:
        """
        Public API: Checks if string represents a GUID.
        
        Args:
            in_string: String to check
            
        Returns:
            True if GUID, False otherwise
        """
        return "Id" == in_string

    @staticmethod
    def reset() -> None:
        """
        Public API: Resets the static node ID counter.
        """
        Node.__static_node_id = 0

    @staticmethod
    def get_static_node_id() -> int:
        """
        Public API: Returns the current static node ID counter.
        
        Returns:
            Current static node ID
        """
        return Node.__static_node_id

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
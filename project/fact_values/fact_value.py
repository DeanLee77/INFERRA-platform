"""
Fact Value Class.
Represents a fact value with type information in PALOS analysis.
Implements access levels and strong typing where appropriate.
"""

import re
from datetime import datetime
from typing import Optional, Any, Union
from project.tokens import Tokenizer, TokenStringDictionary
from project.fact_values.fact_value_type import FactValueType
from project.loggers import Logger

# Protected Module-Level Logger (Access Level: Protected)
_logging: Logger = Logger.get_logger(__name__)

class FactValue:
    """
    FactValue class encapsulates value and type information.
    Implements private state with public accessors.
    
    Access Levels:
    - Public: API methods for external use
    - Protected: Internal helpers (single underscore)
    - Private: Internal state (double underscore)
    """
    
    # -------------------------------------------------------------------------
    # Private Access Level: Instance Variables (Name Mangling)
    # -------------------------------------------------------------------------
    def __init__(self, value: Optional[Any] = None, value_type: Optional[FactValueType] = None):
        """
        Public Constructor: Initializes FactValue with value and type.
        
        Args:
            value: The value to store (any type)
            value_type: The FactValueType of the value
        """
        # Private instance variables (initialized in __init__ to avoid shared state)
        self.__value_type: Optional[FactValueType] = None
        self.__value: Optional[Any] = None
        self.__default_value: Optional[Any] = None
        
        self._initialize_value(value, value_type)

    # -------------------------------------------------------------------------
    # Protected Access Level: Internal Helpers (Single Underscore)
    # -------------------------------------------------------------------------
    def _initialize_value(self, value: Optional[Any], value_type: Optional[FactValueType]) -> None:
        """
        Protected Helper: Initializes value and type with logic.
        
        Args:
            value: The value to store
            value_type: The FactValueType of the value
        """
        if (value is not None) and (value_type is not None):
            self._set_value_with_type(value, value_type)
        elif value is not None:
            self._infer_value_type(value)
        elif value_type is not None:
            self.__value_type = value_type

        if (value is not None) and (value_type is not None):
            _logging.info(f"Initialising FactValue with {str(value)}, type: {self.__value_type.value}")

    def _set_value_with_type(self, value: Any, value_type: FactValueType) -> None:
        """
        Protected Helper: Sets value when type is explicitly provided.
        
        Args:
            value: The value to store
            value_type: The FactValueType of the value
        """
        if value_type == FactValueType.DATE:
            self.__value_type = value_type
        elif isinstance(value, bool):
            self.__value_type = FactValueType.BOOLEAN
        elif isinstance(value, str) and re.match(r"false|true", value, re.IGNORECASE):
            value = False if re.match(r"false", value, re.IGNORECASE) else True
            self.__value_type = FactValueType.BOOLEAN
        else:
            self.__value_type = value_type
        
        self.__default_value = value
        self.__value = value

    def _infer_value_type(self, value: Any) -> None:
        """
        Protected Helper: Infers value type from the value itself.
        
        Args:
            value: The value to infer type from
        """
        if isinstance(value, FactValue):
            self.__value = value.get_value()
            self.__value_type = value.get_value_type()
        elif isinstance(value, bool):
            self.__value = value
            self.__value_type = FactValueType.BOOLEAN
        elif isinstance(value, str) and re.match(r"false|true", value, re.IGNORECASE):
            value = False if re.match(r"false", value, re.IGNORECASE) else True
            self.__value = value
            self.__value_type = FactValueType.BOOLEAN
        elif self.__value_type is not None and self.__value_type == FactValueType.DATE:
            self.__value = datetime.strptime(value, "%d/%m/%Y").strftime("%d/%m/%Y")
            self.__value_type = self.__value_type
        else:
            self.__value = value
            self.__value_type = TokenStringDictionary.find_fact_value_type(
                Tokenizer.get_tokens(str(value)).get_tokens_string())
        
        self.__default_value = value

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Getters)
    # -------------------------------------------------------------------------
    def get_value(self) -> Optional[Any]:
        """
        Public API: Returns the fact value.
        
        Returns:
            The stored value or None
        """
        return self.__value

    def get_value_type(self) -> Optional[FactValueType]:
        """
        Public API: Returns the fact value type.
        
        Returns:
            The FactValueType or None
        """
        return self.__value_type

    def get_default_value(self) -> Optional[Any]:
        """
        Public API: Returns the default value.
        
        Returns:
            The default value or None
        """
        return self.__default_value

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Setters)
    # -------------------------------------------------------------------------
    def set_default_value(self, default_value: Any) -> None:
        """
        Public API: Sets the default value.
        
        Args:
            default_value: The default value to set
        """
        self.__default_value = default_value

    # -------------------------------------------------------------------------
    # Special Methods
    # -------------------------------------------------------------------------
    def __repr__(self) -> str:
        """
        Public API: String representation of the object.
        
        Returns:
            JSON string representation
        """
        return json.dumps({
            "value": self.__value,
            "value_type": self.__value_type.value if self.__value_type else None,
            "default_value": self.__default_value
        })
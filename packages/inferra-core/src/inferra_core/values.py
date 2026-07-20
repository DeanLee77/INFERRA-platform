"""Core-owned fact values and provenance tags."""

from enum import Enum
from typing import Any, Optional


class FactValueType(Enum):
    BOOLEAN = "BOOLEAN"
    INTEGER = "INTEGER"
    DOUBLE = "DOUBLE"
    DECIMAL = "DECIMAL"
    DATE = "DATE"
    STRING = "STRING"
    TEXT = "TEXT"
    DEFI_STRING = "DEFI_STRING"
    HASH = "HASH"
    URL = "URL"
    GUID = "GUID"
    LIST = "LIST"
    WARNING = "WARNING"
    SECTION = "SECTION"
    UNKNOWN = "UNKNOWN"


class FactValue:
    def __init__(
        self,
        value: Any = None,
        value_type: Optional[FactValueType] = None,
    ):
        self.__value: Any = value
        self.__default_value: Any = value
        if value_type is not None:
            self.__value_type: FactValueType = value_type
        elif isinstance(value, bool):
            self.__value_type = FactValueType.BOOLEAN
        elif isinstance(value, int):
            self.__value_type = FactValueType.INTEGER
        elif isinstance(value, float):
            self.__value_type = FactValueType.DOUBLE
        elif isinstance(value, list):
            self.__value_type = FactValueType.LIST
        elif isinstance(value, str):
            self.__value_type = FactValueType.STRING
        else:
            self.__value_type = FactValueType.UNKNOWN

    def get_value(self) -> Any:
        return self.__value

    def set_value(self, value: Any) -> None:
        self.__value = value

    def get_value_type(self) -> FactValueType:
        return self.__value_type

    def set_value_type(self, value_type: FactValueType) -> None:
        self.__value_type = value_type

    def get_default_value(self) -> Any:
        return self.__default_value

    def set_default_value(self, default_value: Any) -> None:
        self.__default_value = default_value

    def __repr__(self) -> str:
        return (
            f"FactValue(value={self.__value}, "
            f"type={self.__value_type}, default_value={self.__default_value})"
        )


class FactSource(Enum):
    """Provenance tag for working-memory entries."""

    ASSERTED = "ASSERTED"
    INFERRED = "INFERRED"
    LEARNED = "LEARNED"
    HYPOTHETICAL = "HYPOTHETICAL"
    SEMANTIC = "SEMANTIC"

    @classmethod
    def from_value(cls, value: object) -> "FactSource":
        """Parse a persisted value, defaulting unknown future values."""
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value))
        except ValueError:
            return cls.INFERRED

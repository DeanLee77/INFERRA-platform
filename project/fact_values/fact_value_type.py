import json

from enum import Enum


class FactValueType(Enum):
    BOOLEAN = "BOOLEAN"
    INTEGER = "INTEGER"
    DEFI_STRING = "DEFI_STRING"
    TEXT = "TEXT"
    STRING = "STRING"
    DOUBLE = "DOUBLE"
    NUMBER = "NUMBER"
    DATE = "DATE"
    DECIMAL = "DECIMAL"
    LIST = "LIST"
    RULE = "RULE"
    RULE_SET = "RULE_SET"
    OBJECT = "OBJECT"
    UNKNOWN = "UNKNOWN"
    URL = "URL"
    HASH = "HASH"
    GUID = "GUID"
    SECTION = "SECTION"
    NULL = "NULL"
    WARNING = "WARNING"

    def __repr__(self):
        return json.dumps(self.__dict__)

    @staticmethod
    def get_all_values():
        return list(map(lambda c: c.value, FactValueType))

    @staticmethod
    def get_all_enums():
        return list(map(lambda c: c, FactValueType))

    @classmethod
    def __contains__(cls, item):
        return item in [v.value for v in cls.__members__.values()]
    

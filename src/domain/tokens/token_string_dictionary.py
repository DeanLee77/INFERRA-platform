from typing import Dict
from src.domain.fact_values.fact_value_type import FactValueType


class TokenStringDictionary:
    __DICTIONARY: Dict[str, FactValueType] = {
        'No': FactValueType.INTEGER,
        'Do': FactValueType.DOUBLE,
        'De': FactValueType.DECIMAL,
        'Da': FactValueType.DATE,
        'Url': FactValueType.URL,
        'Id': FactValueType.GUID,
        'Ha': FactValueType.HASH,
        'Se': FactValueType.SECTION,
        'Q': FactValueType.DEFI_STRING,
        'false': FactValueType.BOOLEAN,
        'FALSE': FactValueType.BOOLEAN,
        'False': FactValueType.BOOLEAN,
        'true': FactValueType.BOOLEAN,
        'TRUE': FactValueType.BOOLEAN,
        'True': FactValueType.BOOLEAN,
        'WARNING': FactValueType.WARNING,
        'L': FactValueType.STRING,
        'M': FactValueType.STRING,
        'U': FactValueType.STRING,
        'C': FactValueType.STRING,
        'Pa': FactValueType.STRING,
        'Fu': FactValueType.STRING,
    }

    @staticmethod
    def find_fact_value_type(token: str) -> FactValueType:
        return TokenStringDictionary.__DICTIONARY.get(token, FactValueType.STRING)

    @classmethod
    def get_all_key_and_values(cls) -> Dict[str, FactValueType]:
        return cls.__DICTIONARY.copy()

    @classmethod
    def _is_known_token(cls, token: str) -> bool:
        return token in cls.__DICTIONARY

    @classmethod
    def _get_default_type(cls) -> FactValueType:
        return FactValueType.STRING

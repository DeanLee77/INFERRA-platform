import string
from project.fact_values.fact_value_type import FactValueType


class TokenStringDictionary:
    dictionary = {
        "No": FactValueType.INTEGER,
        "Do": FactValueType.DOUBLE,
        "De": FactValueType.DECIMAL,
        "Da": FactValueType.DATE,
        "Url": FactValueType.URL,
        "Id": FactValueType.GUID,
        "Ha": FactValueType.HASH,
        "Se": FactValueType.SECTION,
        "Q": FactValueType.DEFI_STRING,
        "false": FactValueType.BOOLEAN,
        "FALSE": FactValueType.BOOLEAN,
        "False": FactValueType.BOOLEAN,
        "true": FactValueType.BOOLEAN,
        "TRUE": FactValueType.BOOLEAN,
        "True": FactValueType.BOOLEAN,
        "WARNING": FactValueType.WARNING,
        "L": FactValueType.STRING,
        "M": FactValueType.STRING,
        "U": FactValueType.STRING,
        "C": FactValueType.STRING
    }

    @staticmethod
    def find_fact_value_type(token: string):
        if token not in TokenStringDictionary().dictionary.keys():
            return FactValueType.STRING
        else:
            return TokenStringDictionary().dictionary[token]

    @classmethod
    def get_all_key_and_values(cls):
        return cls.dictionary

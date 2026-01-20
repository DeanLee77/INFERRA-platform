import re

from datetime import datetime
from project.tokens import Tokenizer, TokenStringDictionary
from project.fact_values.fact_value_type import FactValueType
from project.loggers import Logger

logging: Logger = Logger.get_logger(__name__)


class FactValue:
    # type of this variable is FactValueType
    __value_type: FactValueType = None

    # type of this variable is various.
    # it could be string, int, float, list, dict, bool,
    __value = None
    __default_value = None

    def __init__(self, value=None, value_type=None):
        if (value is not None) and (value_type is not None):
            if value_type == FactValueType.DATE:
                self.__value_type = value_type
            elif isinstance(value, bool):
                self.__value_type = FactValueType.BOOLEAN
            elif isinstance(value, str) and re.match(r"false|true", value, re.IGNORECASE):
                if re.match(r"false", value, re.IGNORECASE):
                    value = False
                else:
                    value = True
                self.__value_type = FactValueType.BOOLEAN
            else:
                self.__value_type = value_type
            self.__default_value = value
            self.__value = value
        elif value is not None:
            if isinstance(value, FactValue):
                self.__value = value.get_value()
                self.__value_type = value.get_value_type()
            elif isinstance(value, bool):
                self.__value = value
                self.__value_type = FactValueType.BOOLEAN
            elif isinstance(value, str) and re.match(r"false|true", value, re.IGNORECASE):
                if re.match(r"false", value, re.IGNORECASE):
                    value = False
                else:
                    value = True
                self.__value = value
                self.__value_type = FactValueType.BOOLEAN
            elif value_type is not None and value_type == FactValueType.DATE:
                self.__value = datetime.strptime(value, "%d/%m/%Y").strftime("%d/%m/%Y")
                self.__value_type = value_type
            else:
                self.__value = value
                self.__value_type = TokenStringDictionary.find_fact_value_type(
                    Tokenizer.get_tokens(str(value)).get_tokens_string())
            self.__default_value = value
        elif value is None and value_type is not None:
            self.__value_type = value_type

        if (value is not None) and (value_type is not None):
            logging.info("Initialising FactValue with " + str(value) + ", type: " + self.__value_type.value)

    # def __repr__(self):
    #     return json.dumps(self.__dict__)
    
    # def __getstate__(self):
    #     state = dict()  # Create a copy of the instance's attribute dictionary

    #     # Serialize specific attributes requiring special treatment
    #     state["__value_type"] = self.__value_type.__getstate__() if self.__value_type != None else None
    #     state["__value"] = self.__value
    #     state["__default_value"] = self.__default_value
    #     return state

    # def __setstate__(self, state):
    #     # Deserialize specific attributes using the serialized data
    #     self.__value_type = state["__value_type"]
    #     self.__value = state["__value"]
    #     self.__default_value = state["__default_value"]

    #     # Remove the temporary keys from the instance
    #     del state["__value_type"]
    #     del state["__value"]
    #     del state["__default_value"]
    #     # Remove other temporary keys added during serialization

    def get_value(self) -> any:
        return self.__value

    def get_value_type(self) -> FactValueType:
        return self.__value_type

    def set_default_value(self, default_value):
        self.__default_value = default_value

    def get_default_value(self) -> any:
        return self.__default_value
    
    # def serialize(self):
    #     # Serialize the object's state to bytes using pickle
    #     return pickle.dumps(self.__dict__)

    # @classmethod
    # def deserialize(cls, serialized):
    #     # Deserialize the serialized data and create an instance of MyClass
    #     obj = cls.__new__(cls)  # Create a new instance of the class
    #     obj.__dict__.update(pickle.loads(serialized))  # Update object's state with deserialized data
    #     return obj

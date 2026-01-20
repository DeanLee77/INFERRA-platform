import re
from project.loggers import Logger
from datetime import datetime
from project.fact_values import FactValue, FactValueType
from . import LineType, MetaType
from .node import Node
from project.tokens import Token


logging: Logger = Logger.get_logger(__name__)


class MetadataLine(Node):
    # Meta type pattern list
    # 1. ULU[NoDaMLDe]
    # 2. U[NoDaMLDe]
    # 3. U

    __metaType: MetaType = None
    __name: str = None

    def __init__(self, node_text: str, tokens: Token):
        super().__init__(parent_text=node_text, tokens=tokens)
        self._lineType = LineType.META

    def initialisation(self, parent_text: str, tokens: Token):
        logging.info("Generating Metadata Line with : " + str(parent_text))
        self.__name = parent_text
        self._nodeName = parent_text
        self.set_meta_type(parent_text)

        if self.__metaType == MetaType.FIXED:
            pattern = re.compile(r"^(FIXED)(.*)(\s[AS|IS]\s*.*)")
            match = pattern.match(parent_text)

            if match:
                self.set_value(match.group(3).strip(), tokens)
                self._variableName = match.group(2).strip()
        if self.__metaType == MetaType.INPUT:
            pattern = re.compile(r"^(INPUT)(.*)(AS)(.*)[(IS)(.*)]?")
            match = pattern.match(parent_text)

            if match:
                self.set_value(match.group(4).strip(), tokens)
                self._variableName = match.group(2).strip()

    def set_value(self, value_in_string: str, tokens: Token):
        token_string_list_size = len(tokens.get_tokens_string_list())
        last_token_string = tokens.get_tokens_string_list()[token_string_list_size - 1]
        temp_array = re.split(' ', value_in_string)
        temp_str = temp_array[0]

        if self.__metaType == MetaType.FIXED:
            if temp_str == "IS":
                if self.is_date(last_token_string):
                    self._value = FactValue(datetime.strptime(temp_array[1], '%d/%m/%Y').strftime('%d/%m/%Y'), FactValueType.DATE)
                elif self.is_double(last_token_string):
                    self._value = FactValue(float(temp_array[1]), FactValueType.DOUBLE)
                elif self.is_integer(last_token_string):
                    self._value = FactValue(int(temp_array[1]), FactValueType.INTEGER)
                elif self.is_boolean(last_token_string):
                    if temp_array[1].lower() == 'false':
                        self._value = FactValue(False, FactValueType.BOOLEAN)
                    else:
                        self._value = FactValue(True, FactValueType.BOOLEAN)

                elif self.is_hash(last_token_string):
                    self._value = FactValue(temp_array[1], FactValueType.HASH)
                elif self.is_url(last_token_string):
                    self._value = FactValue(temp_array[1], FactValueType.URL)
                elif self.is_guid(last_token_string):
                    self._value = FactValue(temp_array[1], FactValueType.GUID)
            elif temp_str == 'AS':
                if temp_array[1] == 'LIST':
                    self._value = FactValue(list(), FactValueType.LIST)
                else:
                    self._value = FactValue('WARNING', FactValueType.WARNING)
        elif self.__metaType == MetaType.INPUT:
            if len(temp_array) > 1:
                # within this case 'DefaultValue' will be set due to the statement format is as follows;
                # 'A AS 'TEXT' IS B'
                # and 'A' is variable, 'TEXT' is a type of variable, and 'B' is a default value.
                # if the type is 'LIST' then variable is a list then the factValue has a default value.

                temp_str_2 = temp_array[2]
                if FactValueType.LIST.value == temp_str:
                    value_list = list()
                    # temp_str_2 is date value
                    if Node.is_date(last_token_string):
                        temp_value = FactValue(datetime.strptime(temp_str_2, '%d/%m/%Y').strftime("%d/%m/%Y"), FactValueType.DATE)
                    # temp_str_2 is double value
                    elif Node.is_double(last_token_string):
                        temp_value = FactValue(float(temp_str_2), FactValueType.DOUBLE)
                    # temp_str_2 is integer value
                    elif Node.is_integer(last_token_string):
                        temp_value = FactValue(int(temp_str_2), FactValueType.INTEGER)
                    # temp_str_2 is hash value
                    elif Node.is_hash(last_token_string):
                        temp_value = FactValue(temp_str_2, FactValueType.HASH)
                    # temp_str_2 is URL value
                    elif Node.is_url(last_token_string):
                        temp_value = FactValue(temp_str_2, FactValueType.URL)
                    # temp_str_2 is GUID value
                    elif Node.is_guid(last_token_string):
                        temp_value = FactValue(temp_str_2, FactValueType.GUID)
                    # temp_str_2 is boolean value
                    elif Node.is_boolean(last_token_string):
                        if temp_str_2.lower() == 'false':
                            temp_value = FactValue(False, FactValueType.BOOLEAN)
                        else:
                            temp_value = FactValue(True, FactValueType.BOOLEAN)
                    # temp_str_2 is string value
                    else:
                        temp_value = FactValue(temp_str_2, FactValueType.STRING)
                    value_list.append(temp_value)
                    self._value = FactValue(value_list, FactValueType.LIST)
                    self._value.set_default_value(temp_value)
                elif FactValueType.TEXT.value == temp_str \
                        or FactValueType.STRING.value == temp_str:
                    self._value = FactValue(temp_str_2, FactValueType.STRING)
                elif FactValueType.DATE.value == temp_str:
                    self._value = FactValue(datetime.strptime(temp_str_2, '%d/%m/%Y').strftime("%d/%m/%Y"), FactValueType.DATE)
                elif FactValueType.NUMBER.value == temp_str \
                        or FactValueType.INTEGER.value == temp_str:
                    self._value = FactValue(int(temp_str_2), FactValueType.INTEGER)
                elif FactValueType.DECIMAL.value == temp_str \
                        or FactValueType.DOUBLE.value == temp_str:
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
                # case of the statement does not have value, only contains a type of the variable
                # so that the value will not have any default values
                if FactValueType.LIST.value == temp_str:
                    self._value = FactValue(list(), FactValueType.LIST)
                elif FactValueType.TEXT.value == temp_str \
                        or FactValueType.STRING.value == temp_str:
                    self._value = FactValue(None, FactValueType.STRING)
                elif FactValueType.URL.value == temp_str:
                    self._value = FactValue(None, FactValueType.URL)
                elif FactValueType.HASH.value == temp_str:
                    self._value = FactValue(None, FactValueType.HASH)
                elif FactValueType.GUID.value == temp_str:
                    self._value = FactValue(None, FactValueType.GUID)
                elif FactValueType.DATE.value == temp_str:
                    self._value = FactValue(None, FactValueType.DATE)
                elif FactValueType.NUMBER.value == temp_str \
                        or FactValueType.INTEGER.value == temp_str:
                    self._value = FactValue(None, FactValueType.INTEGER)
                elif FactValueType.DECIMAL.value == temp_str \
                        or FactValueType.DOUBLE.value == temp_str:
                    self._value = FactValue(None, FactValueType.DOUBLE)
                elif FactValueType.BOOLEAN.value == temp_str:
                    self._value = FactValue(None, FactValueType.BOOLEAN)

    def set_meta_type(self, parent_text):
        for x in MetaType.get_all_meta_type():
            if x.value in parent_text:
                self.__metaType = x
                break

    def get_meta_type(self):
        return self.__metaType

    def get_name(self):
        return self.__name

    def get_line_type(self):
        return LineType.META

    def self_evaluate(self, working_memory):
        return FactValue(None, None)

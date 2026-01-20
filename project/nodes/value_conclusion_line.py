import json
from project.loggers import Logger
from project.nodes.node import Node
from project.nodes.line_type import LineType
from project.fact_values import FactValue
from project.tokens import Token
from project.nodes.meta_data import MetaData

logging: Logger = Logger.get_logger(__name__)


class ValueConclusionLine(Node):
    # ValueConclusionLine format is as follows;
    # 1. 'A-statement IS B-statement';
    # 2. 'A-item name IS IN LIST: B-list name'; or
    # 3. 'A-statement'(plain statement line) including statement of 'A' type from
    # a child nodes of ExprConclusionLine type which are 'NEEDS' and 'WANTS'.
    # When the inference engine reaches at a ValueConclusionLine
    # and needs to ask a question to a user,
    # Hence, the question can be from either variableName or ruleName,
    # and a result of the question will be inserted into the workingMemory.
    # However, when the engine reaches at the line during forward-chaining
    # then the key for the workingMemory will be a ruleName,
    # and value for the workingMemory will be set as a result of propagation.
    #
    # If the rule statement is in a format of 'A-statement'
    # then a default value of variable 'value' will be set as 'false'

    __isPlainStatementFormat = False

    def __init__(self, id: int=None, node_text: str=None, tokens: Token=None, meta_data: MetaData=None):
        super().__init__(id=id, parent_text=node_text, tokens=tokens, meta_data=meta_data)
        self._lineType = LineType.VALUE_CONCLUSION

    def __repr__(self):
        return json.dumps(self.__dict__)

    def initialisation(self, node_text: str, tokens: Token):
        logging.info("Generating ValueConclusion Line with : " + str(node_text))

        # tokens.tokensStringList.size is same as tokens.tokensList.size
        token_string_list_size = len(tokens.get_tokens_string_list())

        # this will exclude 'IS' and 'IS IN  LIST:' within the given 'tokens'
        self.__isPlainStatementFormat = len(list(filter(lambda c: 'IS' in c, tokens.get_tokens_list()))) == 0

        # the line must be a parent line in this case other than a case of the rule contains 'IS IN LIST:'
        if not self.__isPlainStatementFormat:
            self._variableName = node_text[:node_text.index('IS')].strip()
            last_token = tokens.get_tokens_list()[token_string_list_size - 1]

        # this is a case of that the line is in a 'A-statement' format
        else:
            self._variableName = node_text
            last_token = 'False'
        self._nodeName = node_text
        last_token_string = tokens.get_tokens_string_list()[token_string_list_size - 1]
        self.set_value(last_token_string, last_token)

    def get_is_plain_statement(self) -> bool:
        return self.__isPlainStatementFormat

    def get_line_type(self) -> LineType:
        return LineType.VALUE_CONCLUSION

    def self_evaluate(self, working_memory: dict) -> FactValue:
        # Negation and Known type are a part of dependency
        # hence, only checking its variableName value against the workingMemory is necessary.
        # type is as follows;
        #  1. the rule is a plain statement
        #  2. the rule is a statement of 'A IS B'
        #  3. the rule is a statement of 'A IS IN LIST: B'
        #  4. the rule is a statement of 'needs(wants) A'. this is from a child nodes of ExprConclusionLine type
        fv: FactValue = None
        if not self.__isPlainStatementFormat:
            if len(list(filter(lambda c: c == 'IS', list(self._tokens.get_tokens_list())))) > 0:
                fv = self._value
            elif len(list(filter(lambda c: c.find('IS IN LIST') != -1, list(self._tokens.get_tokens_list())))) > 0:
                line_value = False
                list_name = self.get_fact_value().get_value()
                if working_memory[list_name] is not None:
                    variable_value_from_working_memory = working_memory[self._variableName]
                    if variable_value_from_working_memory is not None:
                        line_value = \
                            len(list(filter(lambda fact_value: fact_value.get_value() \
                                                               == variable_value_from_working_memory.get_value(),
                                            working_memory[list_name].get_value()))) > 0
                    else:
                        line_value = \
                            len(list(filter(lambda fact_value: self._variableName == fact_value.get_value(),
                                            working_memory[list_name].get_value()))) > 0
                fv = FactValue(line_value)

            return fv

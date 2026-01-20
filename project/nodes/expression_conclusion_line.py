import json
import re
from datetime import datetime
from project.loggers import Logger
from project.nodes.node import Node
from project.nodes.line_type import LineType
from project.fact_values import FactValue, FactValueType
from project.tokens import Token, Tokenizer
from project.nodes.meta_data import MetaData
import sympy as sp

logging: Logger = Logger.get_logger(__name__)


class ExprConclusionLine(Node):
    __equation: FactValue = None

    __dateFormatter = '%Y-%m-%d'

    def __init__(self, id: int=None, parent_text: str=None, tokens: Token=None, meta_data: MetaData=None):
        super().__init__(id=id, parent_text=parent_text, tokens=tokens, meta_data=meta_data)
        self._lineType = LineType.EXPR_CONCLUSION

    def __repr__(self):
        return json.dumps(self.__dict__)

    def initialisation(self, parent_text: str, tokens: Token):
        logging.info("Generating Expression Conclusion Line with : " + str(parent_text))

        self._nodeName = parent_text
        temp_array = re.split("IS CALC", parent_text)
        self._variableName = temp_array[0].strip()
        index_of_c_in_tokens_string_list = tokens.get_tokens_string_list().index('C')
        self.set_value(tokens.get_tokens_string_list()[index_of_c_in_tokens_string_list].strip(),
                       re.split("IS CALC",tokens.get_tokens_list()[index_of_c_in_tokens_string_list])[1].strip())
        self.__equation = self._value

    def get_equation(self) -> FactValue:
        return self.__equation

    def set_equation(self, equation):
        self.__equation = equation

    def get_line_type(self) -> LineType:
        return LineType.EXPR_CONCLUSION

    def self_evaluate(self, working_memory: dict) -> FactValue:
        # this node_line can evaluate all python syntax as a part of evaluation.
        # however, all calculation is done by SymPy module. The performance has not been proved yet here.
        # Hence, it may require amendment later.

        equation_in_string = self.__equation.get_value()
       
        try:
            symbols = {}
            substituted = equation_in_string
            for i, (var, value) in enumerate (working_memory.items()):
                symbol_name = f'v{i}'
                symbols[symbol_name] = value
                substituted = substituted.replace(var, symbol_name)
            
            substituted = ' '.join(substituted.split())
            expression = sp.parse_expr(substituted)

            subs_dict = {}
            for symbol_name, value in symbols.items():
                if value.get_value_type() == FactValueType.LIST:
                    value_list = {sub_value.get_value() for sub_value in value.get_value()}
                    subs_dict[symbol_name] = value_list
                elif value.get_value() == None:
                    subs_dict[symbol_name] = ''
                else:
                    subs_dict[symbol_name] = value.get_value()
            
            result = expression.subs(subs_dict)
            outcome = result.evalf()
            check_tokens = Tokenizer.get_tokens(str(outcome)).get_tokens_string()

            if check_tokens == 'No':
                return_value = FactValue(outcome, FactValueType.INTEGER)
            elif check_tokens == 'De':
                return_value = FactValue(outcome, FactValueType.DOUBLE)
                # there is no function for outcome to be a date at the moment
                # E.g.The determination IS CALC(enrollment date + 5 days)
            elif check_tokens == 'Da':
                return_value = FactValue(outcome, FactValueType.DATE)
            else:
                return_value = FactValue(outcome, FactValueType.BOOLEAN)

            return return_value
        except Exception as e:
            logging.info(f'Evaluation failed: {e}. \n Highly likely because the Working_Memory has a list value for a certain keys, Node Name: {self.get_node_name()}')
            logging.info(f'Now manually substitute variables in the expression: {equation_in_string}')
            # Sort keys by length (longest first) to avoid partial matches
            sorted_keys = sorted(working_memory, key=len, reverse=True)

            # Build regex: \b(exact|keys|here)\b
            pattern_parts = [re.escape(key) for key in sorted_keys]
            pattern = r'\b(?:' + '|'.join(pattern_parts) + r')\b'
            compiled_pattern = re.compile(pattern)
            def replacer(match):
                key = match.group(0)
                value = working_memory[key]
                if (value.get_value_type() == FactValueType.LIST):
                    value_list = {sub_value.get_value() for sub_value in value.get_value()}
                    return value_list
                elif value.get_value() == None:
                    value = ''
                else:
                    value = value.get_value()
                return str(value)
            
            # Substitute
            substituted = compiled_pattern.sub(replacer, equation_in_string)
            # Normalize spaces for eval (optional, but helps with multi-spaces)
            substituted = ' '.join(substituted.split())
            # Safe eval
            safe_globals = {"__builtins__": {}}  # No builtins for safety
            try:
                outcome = eval(substituted, safe_globals, {})
                check_tokens = Tokenizer.get_tokens(str(outcome)).get_tokens_string()
                if check_tokens == 'No':
                    return_value = FactValue(outcome, FactValueType.INTEGER)
                elif check_tokens == 'De':
                    return_value = FactValue(outcome, FactValueType.DOUBLE)
                    # there is no function for outcome to be a date at the moment
                    # E.g.The determination IS CALC(enrollment date + 5 days)
                elif check_tokens == 'Da':
                    return_value = FactValue(outcome, FactValueType.DATE)
                else:
                    return_value = FactValue(outcome, FactValueType.BOOLEAN)
                
                return return_value
            except Exception as e:
                raise ValueError(f'Evaluation failed: {e}, Node Name: {self.get_node_name()}')

            
            
        
        
        

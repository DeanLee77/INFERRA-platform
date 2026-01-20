import json
from project.loggers import Logger


class Token:
    __tokens_list = []
    __tokens_string_list = []
    __tokens_string = ''

    def __init__(self, tokens_list: []=None, tokens_string_list: []=None, tokens_string: str=None):
        logging: Logger = Logger.get_logger(__name__)\
            # .info("Initiating tokens")
        if (tokens_list is not None) and (tokens_string_list is not None) and (tokens_string is not None):
            self.__tokens_list = tokens_list
            self.__tokens_string_list = tokens_string_list
            self.__tokens_string = tokens_string

    def __repr__(self):
        return json.dumps(self.__dict__)

    def get_tokens_list(self) -> []:
        return self.__tokens_list

    def get_tokens_string_list(self) -> []:
        return self.__tokens_string_list

    def get_tokens_string(self) -> str:
        return self.__tokens_string


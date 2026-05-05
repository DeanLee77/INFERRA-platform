from typing import List, Optional
from src.shared.loggers import Logger

_logger: Logger = Logger.get_logger(__name__)


class Token:
    def __init__(self, tokens_list: Optional[List[str]] = None,
                 tokens_string_list: Optional[List[str]] = None,
                 tokens_string: Optional[str] = None):
        self.__tokens_list: List[str] = tokens_list or []
        self.__tokens_string_list: List[str] = tokens_string_list or []
        self.__tokens_string: str = tokens_string or ""

    def get_tokens_list(self) -> List[str]:
        return self.__tokens_list

    def set_tokens_list(self, tokens_list: List[str]) -> None:
        self.__tokens_list = tokens_list

    def get_tokens_string_list(self) -> List[str]:
        return self.__tokens_string_list

    def set_tokens_string_list(self, tokens_string_list: List[str]) -> None:
        self.__tokens_string_list = tokens_string_list

    def get_tokens_string(self) -> str:
        return self.__tokens_string

    def set_tokens_string(self, tokens_string: str) -> None:
        self.__tokens_string = tokens_string

    def __repr__(self) -> str:
        return f"Token(list={self.__tokens_list}, str_list={self.__tokens_string_list}, str={self.__tokens_string})"

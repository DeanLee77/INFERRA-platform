import re
from project.loggers import Logger
from project.tokens import Token


logging: Logger = Logger.get_logger(__name__)

META_DATA_TYPES = [
    ('# Reference', '_reference'),
    ('# Section', '_origin'),
    ('# Original', '_statement')
]

class MetaData:
    _reference: str = None
    _origin: str = None
    _statement: str = None

    def __init__(self, reference: str=None, origin: str=None, statement: str=None):
        
        self._reference = reference if reference != None else None
        self._origin = origin if origin!= None else None
        self._statement = statement if statement!= None else None

    def set_reference(self, reference: str):
        self._reference = reference

    def get_reference(self) -> str:
        return self._reference
    
    def set_origin(self, origin: str):
        self._origin = origin
    
    def get_origin(self) -> str:
        return self._origin

    def set_statement(self, statement):
        self._statement = statement

    def get_statement(self) -> str:
        return self._statement
    
    def instantiate_attrs(self, line: str):
        for meta_type, attr in META_DATA_TYPES:
            if line.startswith(meta_type):
                # Extract content after the metadata type and optional colon/space
                content = line[len(meta_type):].lstrip(': ').strip()
                setattr(self, attr, content)
                break


    @staticmethod
    def is_meta_data(line: str):
        return any(meta_type in line for meta_type, attr in META_DATA_TYPES)

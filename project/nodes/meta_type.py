from enum import Enum

class MetaType(Enum):
    LINE = 'LINE'
    FIXED = 'FIXED'
    INPUT = 'INPUT'
    ITEM = 'ITEM'
    GOAL = 'GOAL'
    CLICK_LINK = 'CLICK_LINK'
    DOC = 'DOC'
    IMPORT = 'IMPORT'

    @staticmethod
    def get_all_meta_type():
        return list(map(lambda c: c, MetaType))

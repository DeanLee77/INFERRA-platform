from abc import ABCMeta
import abc


class ILineReader(metaclass=ABCMeta):
    @abc.abstractmethod
    def get_next_line(self): pass




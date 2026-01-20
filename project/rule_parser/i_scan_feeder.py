from abc import ABCMeta
import abc
from project.nodes.meta_data import MetaData


class IScanFeeder(metaclass=ABCMeta):
    @abc.abstractmethod
    def handle_parent(self, parent_text, line_number, meta_data: MetaData): pass

    @abc.abstractmethod
    def handle_child(self, parent_text, child_text, first_keywords_group, line_number): pass

    @abc.abstractmethod
    def handle_list_item(self, parent_text, item_text, meta_type): pass

    @abc.abstractmethod
    def handle_warning(self, parent_text): pass

    @abc.abstractmethod
    def get_node_set(self): pass

    @abc.abstractmethod
    def set_node_set(self, ns): pass

    @abc.abstractmethod
    def create_dependency_matrix(self): pass
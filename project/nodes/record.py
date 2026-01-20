import json
from project.loggers import Logger

logging: Logger = Logger.get_logger(__name__)

class HistoryRecord:
    __name = None
    __type = None
    __trueCount = 0
    __falseCount = 0

    def __init__(self, name=None, type=None, true_count=None, false_count=None):
        self.__name = name
        self.__type = type
        self.__trueCount = true_count
        self.__falseCount = false_count
        logging.info("Generating Record : "
                     "Name-"+str(name)+", "
                     "Type-"+str(type)+", "
                     "True Count-"+str(true_count)+", "
                     "False Count-"+str(false_count))

    def __repr__(self):
        return json.dumps(self.__dict__)

    def set_name(self, name):
        self.__name = name

    def get_name(self):
        return self.__name

    def set_type(self, type):
        self.__type = type

    def get_type(self):
        return self.__type

    def set_true_count(self, true_count):
        self.__trueCount = true_count

    def get_true_count(self):
        return self.__trueCount

    def add_true_count(self, true_count):
        self.__trueCount += true_count

    def increment_true_count(self):
        self.__trueCount = self.__trueCount + 1

    def set_false_count(self, false_count):
        self.__falseCount = false_count

    def add_false_count(self, false_count):
        self.__falseCount += false_count

    def increment_false_count(self):
        self.__falseCount = self.__falseCount + 1

    def get_false_count(self):
        return self.__falseCount

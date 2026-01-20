import json


class DependencyType:
    __mandatoryDependency = 64  # 1000000
    __optionalDependency = 32  # 0100000
    __possibleDependency = 16  # 0010000
    __andDependency = 8  # 0001000
    __orDependency = 4  # 0000100
    __notDependency = 2  # 0000010
    __knownDependency = 1  # 0000001
    __dependencyArray = []

    def __init__(self): pass

    def __repr__(self):
        return json.dumps(self.__dict__)

    @classmethod
    def get_mandatory(cls) -> int:
        return cls.__mandatoryDependency

    @classmethod
    def get_optional(cls) -> int:
        return cls.__optionalDependency

    @classmethod
    def get_possible(cls) -> int:
        return cls.__possibleDependency

    @classmethod
    def get_and(cls) -> int:
        return cls.__andDependency

    @classmethod
    def get_or(cls) -> int:
        return cls.__orDependency

    @classmethod
    def get_not(cls) -> int:
        return cls.__notDependency

    @classmethod
    def get_known(cls) -> int:
        return cls.__knownDependency

    @classmethod
    def populating_dependency(cls) -> None:
        cls.__dependencyArray.append(cls.get_and())
        cls.__dependencyArray.append(cls.get_or())
        cls.__dependencyArray.append(cls.get_not())
        cls.__dependencyArray.append(cls.get_known())
        cls.__dependencyArray.append(cls.get_mandatory())
        cls.__dependencyArray.append(cls.get_optional())
        cls.__dependencyArray.append(cls.get_possible())

    @classmethod
    def get_dependency_array(cls) -> []:
        return cls.__dependencyArray

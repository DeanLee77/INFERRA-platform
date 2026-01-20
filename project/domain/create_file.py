class CreateFile:
    __ruleName: str = ""
    __ruleText: str = ""

    def __init__(self): pass

    def get_rule_name(self):
        return self.__ruleName

    def set_rule_name(self, rule_name: str):
        self.__ruleName = rule_name

    def get_rule_text(self):
        return self.__ruleText

    def set_rule_text(self, rule_text: str):
        self.__ruleText = rule_text

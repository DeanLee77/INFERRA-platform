class UpdateRuleDescription:
    __newRuleName: str = ""
    __oldRuleName: str = ""
    __newRuleCategory: str = ""

    def __init__(self): pass

    def get_new_rule_name(self):
        return self.__newRuleName

    def set_new_rule_name(self, new_rule_name: str):
        self.__newRuleName = new_rule_name

    def get_old_rule_name(self):
        return self.__oldRuleName

    def set_old_rule_name(self, old_rule_name: str):
        self.__oldRuleName = old_rule_name

    def get_new_category(self):
        return self.__newRuleCategory

    def set_new_category(self, new_category: str):
        self.__newRuleCategory = new_category



from src.adapters.outbound.persistence.models import UserORM, RuleORM, FileORM, HistoryORM


class TestUserORMInit:
    def test_init_sets_email_and_password(self):
        user = UserORM(email="test@example.com", password="secret")
        assert user.email == "test@example.com"
        assert user.password == "secret"


class TestRuleORMGetLatestFile:
    def test_get_latest_file_returns_last_file(self):
        rule = RuleORM(rule_name="test_rule", rule_category="cat", rule_description="desc")
        file1 = FileORM(rule_id=1, files=b"data1")
        file2 = FileORM(rule_id=1, files=b"data2")
        rule.rule_files = [file1, file2]
        result = rule.get_latest_file()
        assert result is file2

    def test_get_latest_file_returns_none_when_empty(self):
        rule = RuleORM(rule_name="test_rule")
        rule.rule_files = []
        result = rule.get_latest_file()
        assert result is None


class TestRuleORMGetLatestHistory:
    def test_get_latest_history_returns_last_history(self):
        rule = RuleORM(rule_name="test_rule")
        hist1 = HistoryORM(rule_id=1, history={"step": 1})
        hist2 = HistoryORM(rule_id=1, history={"step": 2})
        rule.rule_histories = [hist1, hist2]
        result = rule.get_latest_history()
        assert result is hist2

    def test_get_latest_history_returns_none_when_empty(self):
        rule = RuleORM(rule_name="test_rule")
        rule.rule_histories = []
        result = rule.get_latest_history()
        assert result is None

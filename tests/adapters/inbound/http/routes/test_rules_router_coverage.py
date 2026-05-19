from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.adapters.inbound.http.routes import rules


@pytest.mark.asyncio
async def test_find_latest_rule_file_decodes_file():
    service = MagicMock()
    rule_file = MagicMock(file_id=10, rule_id=20)
    service.get_latest_rule_file.return_value = rule_file
    service.decode_rule_file.return_value = "rule text"

    with patch("src.adapters.inbound.http.routes.rules._service", return_value=service):
        response = await rules.find_the_latest_rule_file_by_name("rule", db=MagicMock())

    assert response.fileId == 10
    assert response.ruleId == 20
    assert response.ruleText == "rule text"


@pytest.mark.asyncio
async def test_find_latest_rule_history_shapes_response():
    service = MagicMock()
    rule = SimpleNamespace(rule_id=7, name="rule")
    service.get_latest_rule_history.return_value = {
        "rule": rule,
        "history": {"changed": True},
    }

    with patch("src.adapters.inbound.http.routes.rules._service", return_value=service):
        response = await rules.find_the_latest_rule_history_by_name("rule", db=MagicMock())

    assert response.ruleId == 7
    assert response.ruleName == "rule"
    assert response.history == {"changed": True}

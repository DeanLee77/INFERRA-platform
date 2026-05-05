from unittest.mock import MagicMock, patch

from src.dependencies import get_session_store, reset_singletons
from src.domain.state.feature_flags import FeatureFlags


def test_get_session_store_uses_in_memory_by_default():
    reset_singletons()
    with patch("src.dependencies.get_feature_flags", return_value=FeatureFlags(redis_session_store=False)):
        store = get_session_store()

    assert store.__class__.__name__ == "InMemorySessionStore"


def test_get_session_store_uses_redis_when_flag_enabled():
    reset_singletons()
    with patch("src.dependencies.get_feature_flags", return_value=FeatureFlags(redis_session_store=True)):
        with patch("src.dependencies.RedisSessionStore", return_value=MagicMock(name="redis_store")) as redis_store:
            store = get_session_store()

    assert store is redis_store.return_value

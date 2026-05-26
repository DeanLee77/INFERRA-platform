"""
Rule event publisher.

Public API for publishing RuleUpdated events. Gated by the
ASYNC_SYNC_ENABLED feature flag. When the flag is false or Celery
is not installed, this is a no-op.
"""

from typing import Optional

import structlog

from src.domain.state.feature_flags import FeatureFlags
from src.tasks.rule_sync import publish_rule_updated_event

log = structlog.get_logger()


def on_rule_updated(
    rule_name: str,
    rule_text: str,
    feature_flags: Optional[FeatureFlags] = None,
) -> Optional[str]:
    """
    Publish a RuleUpdated event for async RDF sync.

    Called synchronously during rule save — returns immediately.
    The actual RDF compilation happens in the Celery worker.

    Args:
        rule_name: Name of the rule that was updated
        rule_text: Full text content of the rule
        feature_flags: FeatureFlags snapshot (uses default if None)

    Returns:
        Celery task ID if published, None otherwise
    """
    return publish_rule_updated_event(rule_name, rule_text, feature_flags)

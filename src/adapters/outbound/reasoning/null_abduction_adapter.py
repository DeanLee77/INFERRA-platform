import structlog
from typing import Any, Dict, List

from src.ports.abduction_port import AbductionPort

log = structlog.get_logger(__name__)


class NullAbductionAdapter(AbductionPort):
    """Zero-dependency fallback for ABDUCTION_ENABLED=false."""

    def propose_hypotheses(
        self,
        target: str,
        working_memory: Dict[str, Any],
        graph_snapshot: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        log.info(
            "abduction_disabled",
            target=target,
            session_id="",
            node_id=target,
            fact_source="",
            correlation_id="",
        )
        return []

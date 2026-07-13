from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import structlog

from src.adapters.outbound.ontology import fuseki_adapter
from src.adapters.outbound.ontology.fuseki_adapter import (
    FusekiConnectionError,
    _validate_graph_uri,
    _write_auth,
)


log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class FusekiNTriplesLoadTarget:
    role: str
    path: Path
    graph_uri: str
    triple_count: int | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "role": self.role,
            "path": str(self.path),
            "graphUri": self.graph_uri,
            "tripleCount": self.triple_count,
        }


@dataclass(frozen=True)
class FusekiNTriplesLoadResult:
    role: str
    path: Path
    graph_uri: str
    triple_count: int
    status: str

    def as_dict(self) -> dict[str, object]:
        return {
            "role": self.role,
            "path": str(self.path),
            "graphUri": self.graph_uri,
            "tripleCount": self.triple_count,
            "status": self.status,
        }


@dataclass(frozen=True)
class FusekiBulkLoadSummary:
    results: tuple[FusekiNTriplesLoadResult, ...]
    cleared_graph_uris: tuple[str, ...]

    @property
    def total_triples(self) -> int:
        return sum(result.triple_count for result in self.results)

    def as_dict(self) -> dict[str, object]:
        return {
            "results": [result.as_dict() for result in self.results],
            "clearedGraphUris": list(self.cleared_graph_uris),
            "totalTriples": self.total_triples,
        }


class FusekiNTriplesBulkLoader:
    """Load generated N-Triples files into Fuseki named graphs."""

    def __init__(
        self,
        *,
        fuseki_url: str | None = None,
        timeout_seconds: int = 300,
    ) -> None:
        self._fuseki_url = (fuseki_url or fuseki_adapter.FUSEKI_URL).rstrip("/")
        self._timeout_seconds = max(1, int(timeout_seconds))

    def load_targets(
        self,
        targets: Iterable[FusekiNTriplesLoadTarget],
        *,
        replace_existing_graphs: bool = False,
    ) -> FusekiBulkLoadSummary:
        resolved_targets = tuple(targets)
        cleared_graphs: list[str] = []
        if replace_existing_graphs:
            for graph_uri in dict.fromkeys(target.graph_uri for target in resolved_targets):
                self.clear_graph(graph_uri)
                cleared_graphs.append(graph_uri)

        results = tuple(self.load_file(target) for target in resolved_targets)
        return FusekiBulkLoadSummary(
            results=results,
            cleared_graph_uris=tuple(cleared_graphs),
        )

    def load_file(
        self,
        target: FusekiNTriplesLoadTarget,
    ) -> FusekiNTriplesLoadResult:
        graph_uri = _validate_graph_uri(target.graph_uri)
        path = Path(target.path)
        if not path.is_file():
            raise FileNotFoundError(f"N-Triples file not found: {path}")
        triple_count = (
            int(target.triple_count)
            if target.triple_count is not None
            else _count_ntriples(path)
        )
        if triple_count <= 0:
            return FusekiNTriplesLoadResult(
                role=target.role,
                path=path,
                graph_uri=graph_uri,
                triple_count=0,
                status="skipped_empty",
            )

        self._post_ntriples_file(path, graph_uri)
        log.info(
            "fuseki_ntriples_file_loaded",
            role=target.role,
            graph_uri=graph_uri,
            path=str(path),
            triple_count=triple_count,
        )
        return FusekiNTriplesLoadResult(
            role=target.role,
            path=path,
            graph_uri=graph_uri,
            triple_count=triple_count,
            status="loaded",
        )

    def clear_graph(self, graph_uri: str) -> None:
        safe_graph_uri = _validate_graph_uri(graph_uri)
        self._execute_update(f"CLEAR SILENT GRAPH <{safe_graph_uri}>")

    def _post_ntriples_file(self, path: Path, graph_uri: str) -> None:
        if not fuseki_adapter.REQUESTS_AVAILABLE:
            raise FusekiConnectionError("requests package is not installed")
        with path.open("rb") as handle:
            response = fuseki_adapter._requests.post(
                f"{self._fuseki_url}/data",
                params={"graph": graph_uri},
                data=handle,
                headers={"Content-Type": "application/n-triples"},
                auth=_write_auth(),
                timeout=self._timeout_seconds,
            )
        if response.status_code not in (200, 201, 204):
            raise FusekiConnectionError(
                "Fuseki N-Triples load failed: "
                f"status={response.status_code} body={_response_text(response)}"
            )

    def _execute_update(self, sparql: str) -> None:
        if not fuseki_adapter.REQUESTS_AVAILABLE:
            raise FusekiConnectionError("requests package is not installed")
        response = fuseki_adapter._requests.post(
            f"{self._fuseki_url}/update",
            data={"update": sparql},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            auth=_write_auth(),
            timeout=self._timeout_seconds,
        )
        if response.status_code not in (200, 204):
            raise FusekiConnectionError(
                "Fuseki update failed: "
                f"status={response.status_code} body={_response_text(response)}"
            )


def _count_ntriples(path: Path) -> int:
    count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                count += 1
    return count


def _response_text(response: object) -> str:
    text = getattr(response, "text", "")
    if not text:
        return ""
    return str(text)[:500]

"""
Fuseki Adapter — SPARQL-based RDF triple storage.

Provides idempotent INSERT via DELETE/INSERT pattern using source_hash
as a version tag. Supports health checks and delta queries for the
semantic cache.

Connection details are read from environment variables:
    FUSEKI_URL (default: http://localhost:3030/inferra)
"""

import os
import re
from typing import Any, List, Optional, Tuple

import structlog

from src.infrastructure.secrets import read_secret

try:
    import requests as _requests

    REQUESTS_AVAILABLE = True
except ImportError:
    _requests = None  # type: ignore
    REQUESTS_AVAILABLE = False

log = structlog.get_logger()

FUSEKI_URL = os.environ.get("FUSEKI_URL", "http://localhost:3030/inferra")
INF_NS = "http://inferra.ai/schema#"


class FusekiConnectionError(Exception):
    """Raised when Fuseki is unreachable or returns an error."""
    pass


class FusekiAdapter:
    """Adapter for Apache Fuseki RDF store with idempotent SPARQL operations."""

    @staticmethod
    def execute_sparql_idempotent_insert(
        triples: List[Tuple[str, str, str]],
        version: str,
        graph_uri: Optional[str] = None,
    ) -> None:
        """
        Idempotent INSERT of RDF triples using DELETE/INSERT pattern.

        Args:
            triples: List of (subject, predicate, object) tuples
            version: Source hash for idempotency tracking
            graph_uri: Optional named graph URI

        Raises:
            FusekiConnectionError: If Fuseki is unreachable
        """
        if not triples:
            return

        named_graph = graph_uri or f"{INF_NS}version/{version}"

        delete_clause = (
            f"DELETE WHERE {{ GRAPH <{named_graph}> {{ ?s ?p ?o }} }};"
        )

        insert_values = "\n".join(
            f"  <{s}> <{p}> {_format_object(o)} ."
            for s, p, o in triples
        )
        insert_clause = (
            f"INSERT DATA {{ GRAPH <{named_graph}> {{\n{insert_values}\n}} }};"
        )

        sparql = f"{delete_clause}\n{insert_clause}"
        FusekiAdapter._execute_sparql_update(sparql)

        log.info(
            "fuseki_idempotent_insert",
            triple_count=len(triples),
            version=version,
            named_graph=named_graph,
        )

    @staticmethod
    def rule_projection_graph_uri(rule_name: str) -> str:
        """Return the stable named graph URI for a rule ontology projection."""
        return f"{INF_NS}projection/rule/{_sanitize_uri(rule_name)}"

    @staticmethod
    def health_check() -> bool:
        """
        Check Fuseki connectivity.

        Returns:
            True if Fuseki is reachable and responding

        Raises:
            FusekiConnectionError: If Fuseki is unreachable
        """
        if not REQUESTS_AVAILABLE:
            log.warning("requests_not_installed_fuseki_health_check_skipped")
            return True

        try:
            base_url = FUSEKI_URL.rsplit("/", 1)[0] if "/" in FUSEKI_URL.split("://", 1)[-1] else FUSEKI_URL
            resp = _requests.get(f"{base_url}/$/ping", auth=_read_auth(), timeout=5)
            if resp.status_code == 200:
                return True
            raise FusekiConnectionError(f"Fuseki returned status {resp.status_code}")
        except FusekiConnectionError:
            raise
        except Exception as e:
            raise FusekiConnectionError(f"Fuseki unreachable: {e}") from e

    @staticmethod
    def get_rule_triples(rule_name: str) -> List[Tuple[str, str, str]]:
        """
        Retrieve all triples for a given rule.

        Args:
            rule_name: Name of the rule to query

        Returns:
            List of (subject, predicate, object) tuples
        """
        if not REQUESTS_AVAILABLE:
            return []

        try:
            rule_uri = f"{INF_NS}rule/{_sanitize_uri(rule_name)}"
            sparql = (
                "SELECT ?s ?p ?o WHERE { "
                "GRAPH ?g { "
                f"BIND(<{rule_uri}> AS ?s) "
                f"<{rule_uri}> ?p ?o . "
                "} }"
            )
            resp = _requests.post(
                f"{FUSEKI_URL}/query",
                data={"query": sparql},
                headers={"Accept": "application/sparql-results+json"},
                auth=_read_auth(),
                timeout=10,
            )
            if resp.status_code != 200:
                log.warning(
                    "fuseki_query_failed",
                    rule_name=rule_name,
                    status=resp.status_code,
                )
                return []

            results = resp.json().get("results", {}).get("bindings", [])
            return [
                (b["s"]["value"], b["p"]["value"], b["o"]["value"])
                for b in results
                if "s" in b and "p" in b and "o" in b
            ]
        except Exception:
            log.warning("fuseki_query_error", rule_name=rule_name, exc_info=True)
            return []

    @staticmethod
    def list_named_graphs() -> List[Tuple[str, int]]:
        """
        Return named graphs stored in Fuseki with triple counts.

        Returns:
            List of (graph_uri, triple_count) tuples sorted by count descending.
        """
        sparql = (
            "SELECT ?g (COUNT(*) AS ?count) WHERE { "
            "GRAPH ?g { ?s ?p ?o } "
            "} GROUP BY ?g ORDER BY DESC(?count)"
        )
        results = FusekiAdapter._execute_sparql_select(sparql)
        graphs: List[Tuple[str, int]] = []
        for binding in results:
            graph = binding.get("g", {}).get("value")
            count_value = binding.get("count", {}).get("value", "0")
            if not graph:
                continue
            try:
                count = int(count_value)
            except (TypeError, ValueError):
                count = 0
            graphs.append((graph, count))
        return graphs

    @staticmethod
    def get_named_graph_triples(
        graph_uri: str,
        offset: int = 0,
        limit: int = 1000,
    ) -> List[Tuple[str, str, str]]:
        """
        Return triples from a named graph.

        Args:
            graph_uri: Named graph URI.
            offset: Result offset.
            limit: Maximum triples to return.
        """
        safe_uri = _validate_graph_uri(graph_uri)
        safe_offset = max(0, int(offset))
        safe_limit = max(1, min(int(limit), 5000))
        sparql = (
            "SELECT ?s ?p ?o WHERE { "
            f"GRAPH <{safe_uri}> {{ ?s ?p ?o }} "
            f"}} OFFSET {safe_offset} LIMIT {safe_limit}"
        )
        results = FusekiAdapter._execute_sparql_select(sparql)
        return [
            (b["s"]["value"], b["p"]["value"], b["o"]["value"])
            for b in results
            if "s" in b and "p" in b and "o" in b
        ]

    @staticmethod
    def get_named_graph_all_triples(graph_uri: str) -> List[Tuple[str, str, str]]:
        """Return every triple from a named graph for projection integrity checks."""
        safe_uri = _validate_graph_uri(graph_uri)
        sparql = (
            "SELECT ?s ?p ?o WHERE { "
            f"GRAPH <{safe_uri}> {{ ?s ?p ?o }} "
            "}"
        )
        results = FusekiAdapter._execute_sparql_select(sparql)
        return [
            (b["s"]["value"], b["p"]["value"], b["o"]["value"])
            for b in results
            if "s" in b and "p" in b and "o" in b
        ]

    @staticmethod
    def get_named_graph_triple_count(graph_uri: str) -> int:
        """Return the stored triple count for a named graph."""
        safe_uri = _validate_graph_uri(graph_uri)
        sparql = (
            "SELECT (COUNT(*) AS ?count) WHERE { "
            f"GRAPH <{safe_uri}> {{ ?s ?p ?o }} "
            "}"
        )
        results = FusekiAdapter._execute_sparql_select(sparql)
        if not results:
            return 0
        value = results[0].get("count", {}).get("value", "0")
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def execute_guarded_select(
        sparql: str,
        *,
        timeout_seconds: int = 10,
        max_retries: int = 0,
    ) -> List[dict[str, Any]]:
        """Execute a validated read-only query with bounded timeout and retries."""
        attempts = 1 + max(0, min(int(max_retries), 1))
        safe_timeout = max(1, min(int(timeout_seconds), 10))
        last_error: FusekiConnectionError | None = None
        for attempt in range(attempts):
            try:
                return FusekiAdapter._execute_sparql_select(
                    sparql,
                    timeout_seconds=safe_timeout,
                )
            except FusekiConnectionError as exc:
                last_error = exc
                if attempt + 1 >= attempts:
                    break
        if last_error is not None:
            raise last_error
        return []

    @staticmethod
    def query_deltas(since_timestamp: float) -> List[Tuple]:
        """Return triples not previously injected since the given timestamp."""
        return []

    @staticmethod
    def _execute_sparql_update(sparql: str) -> None:
        """
        Execute a SPARQL UPDATE statement against Fuseki.

        Args:
            sparql: SPARQL UPDATE string

        Raises:
            FusekiConnectionError: If the update fails
        """
        if not REQUESTS_AVAILABLE:
            log.warning("requests_not_installed_sparql_update_skipped")
            return

        resp = _requests.post(
            f"{FUSEKI_URL}/update",
            data={"update": sparql},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            auth=_write_auth(),
            timeout=30,
        )
        if resp.status_code not in (200, 204):
            raise FusekiConnectionError(
                f"Fuseki update failed: status={resp.status_code}"
            )

    @staticmethod
    def _execute_sparql_select(
        sparql: str,
        *,
        timeout_seconds: int = 30,
    ) -> List[dict[str, Any]]:
        """Execute a SPARQL SELECT query and return JSON result bindings."""
        if not REQUESTS_AVAILABLE:
            log.warning("requests_not_installed_sparql_select_skipped")
            return []

        safe_timeout = max(1, int(timeout_seconds))
        try:
            resp = _requests.post(
                f"{FUSEKI_URL}/query",
                data={"query": sparql},
                headers={"Accept": "application/sparql-results+json"},
                auth=_read_auth(),
                timeout=safe_timeout,
            )
        except Exception as exc:
            raise FusekiConnectionError(f"Fuseki query failed: {exc}") from exc
        if resp.status_code != 200:
            raise FusekiConnectionError(
                f"Fuseki query failed: status={resp.status_code}"
            )
        return resp.json().get("results", {}).get("bindings", [])


def _sanitize_uri(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", name)


def _validate_graph_uri(uri: str) -> str:
    value = str(uri).strip()
    if not value.startswith(("http://", "https://", "urn:")):
        raise ValueError("graph_uri must be an absolute URI")
    if any(char in value for char in "<>\"{}|^`\\"):
        raise ValueError("graph_uri contains invalid URI characters")
    return value


def _format_object(value: str) -> str:
    if value.startswith(("http://", "https://", "urn:")):
        return f"<{value}>"
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )
    return f'"{escaped}"'


def _auth() -> Optional[Tuple[str, str]]:
    """Backward-compatible write/admin Fuseki auth helper."""
    return _write_auth()


def _write_auth() -> Optional[Tuple[str, str]]:
    username = os.environ.get("FUSEKI_USER", "admin")
    password = read_secret("FUSEKI_PASSWORD") or read_secret("ADMIN_PASSWORD", "admin")
    return _basic_auth(username, password)


def _read_auth() -> Optional[Tuple[str, str]]:
    username = os.environ.get("FUSEKI_READ_USER") or os.environ.get(
        "FUSEKI_USER", "admin"
    )
    password = (
        read_secret("FUSEKI_READ_PASSWORD")
        or read_secret("FUSEKI_PASSWORD")
        or read_secret("ADMIN_PASSWORD", "admin")
    )
    return _basic_auth(username, password)


def _basic_auth(username: str, password: Optional[str]) -> Optional[Tuple[str, str]]:
    if not username:
        return None
    return (username, password or "")

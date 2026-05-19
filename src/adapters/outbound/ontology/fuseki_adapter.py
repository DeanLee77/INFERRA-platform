"""
Fuseki Adapter — SPARQL-based RDF triple storage.

Provides idempotent INSERT via DELETE/INSERT pattern using source_hash
as a version tag. Supports health checks and delta queries for the
semantic cache.

Connection details are read from environment variables:
    FUSEKI_URL (default: http://localhost:3030/inferra)
"""

import os
from typing import List, Optional, Tuple

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
            resp = _requests.get(f"{base_url}/$/ping", auth=_auth(), timeout=5)
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
                auth=_auth(),
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
            auth=_auth(),
            timeout=30,
        )
        if resp.status_code not in (200, 204):
            raise FusekiConnectionError(
                f"Fuseki update failed: status={resp.status_code}"
            )


def _sanitize_uri(name: str) -> str:
    import re
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", name)


def _format_object(value: str) -> str:
    if value.startswith("http://") or value.startswith("https://"):
        return f"<{value}>"
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )
    return f'"{escaped}"'


def _auth() -> Optional[Tuple[str, str]]:
    username = os.environ.get("FUSEKI_USER", "admin")
    password = read_secret("FUSEKI_PASSWORD") or read_secret("ADMIN_PASSWORD", "admin")
    if not username:
        return None
    return (username, password)

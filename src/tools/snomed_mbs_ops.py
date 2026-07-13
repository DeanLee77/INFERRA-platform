from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.adapters.outbound.ontology import fuseki_adapter
from src.adapters.outbound.ontology.fuseki_adapter import FusekiAdapter
from src.adapters.outbound.ontology.fuseki_bulk_loader import (
    FusekiNTriplesBulkLoader,
    FusekiNTriplesLoadTarget,
)
from src.services.snomed_mbs_ingestion_service import (
    EXPORT_ROLE_GRAPH_KEYS,
    SnomedMbsIngestionService,
)


DEFAULT_MANIFEST_NAME = "snomed-mbs-export-manifest.json"
DEFAULT_SNOMED_GRAPH_URI = "http://inferra.ai/ontology/snomed-ct-au/20260630/snapshot"
DEFAULT_MAP_REFSETS_GRAPH_URI = (
    "http://inferra.ai/ontology/snomed-ct-au/20260630/map-refsets"
)
DEFAULT_MBS_GRAPH_URI = "http://inferra.ai/ontology/mbs/20260701"
DEFAULT_MBS_ITEM_NUMBER = "23"
DEFAULT_SNOMED_CONCEPT_ID = "71388002"


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    result = args.handler(args)
    if result is not None:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.tools.snomed_mbs_ops",
        description="SNOMED CT-AU / MBS export, Fuseki load, and verification operations.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover = subparsers.add_parser("discover", help="Inspect local release inputs.")
    _add_common_source_args(discover)
    discover.set_defaults(handler=_handle_discover)

    export = subparsers.add_parser("export", help="Export RDF N-Triples files.")
    _add_common_source_args(export)
    export.add_argument("--output-dir", default=None)
    export.add_argument("--limit", type=int, default=None)
    export.add_argument("--include-attributes", action="store_true")
    export.add_argument("--skip-snomed", action="store_true")
    export.add_argument("--skip-map-refsets", action="store_true")
    export.add_argument("--skip-mbs-schedule", action="store_true")
    export.add_argument("--skip-phi-clinical-categories", action="store_true")
    export.add_argument("--manifest-path", default=None)
    export.add_argument("--mbs-map-refset-id", action="append", default=[])
    export.set_defaults(handler=_handle_export)

    load = subparsers.add_parser("load", help="Load exported N-Triples into Fuseki.")
    load.add_argument("--manifest-path", required=True)
    load.add_argument("--fuseki-url", default="http://localhost:3030/inferra")
    load.add_argument("--replace", action="store_true")
    load.add_argument("--smoke-prefix", default=None)
    load.add_argument("--timeout-seconds", type=int, default=300)
    load.set_defaults(handler=_handle_load)

    verify = subparsers.add_parser("verify", help="Verify Fuseki graph counts.")
    verify.add_argument("--manifest-path", required=True)
    verify.add_argument("--fuseki-url", default="http://localhost:3030/inferra")
    verify.add_argument("--smoke-prefix", default=None)
    verify.set_defaults(handler=_handle_verify)

    verify_integration = subparsers.add_parser(
        "verify-integration",
        help="Run live SNOMED CT-AU / MBS multi-graph integration checks.",
    )
    verify_integration.add_argument("--fuseki-url", default="http://localhost:3030/inferra")
    verify_integration.add_argument("--snomed-graph-uri", default=DEFAULT_SNOMED_GRAPH_URI)
    verify_integration.add_argument(
        "--map-refsets-graph-uri",
        default=DEFAULT_MAP_REFSETS_GRAPH_URI,
    )
    verify_integration.add_argument("--mbs-graph-uri", default=DEFAULT_MBS_GRAPH_URI)
    verify_integration.add_argument("--mbs-item-number", default=DEFAULT_MBS_ITEM_NUMBER)
    verify_integration.add_argument("--snomed-concept-id", default=DEFAULT_SNOMED_CONCEPT_ID)
    verify_integration.add_argument("--timeout-seconds", type=int, default=10)
    verify_integration.set_defaults(handler=_handle_verify_integration)

    return parser


def _add_common_source_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--package", default=None, dest="package_preference")
    parser.add_argument("--mbs-xml-path", default=None)
    parser.add_argument("--mbs-xml-url", default=None)
    parser.add_argument("--phi-clinical-categories-path", default=None)


def _handle_discover(args: argparse.Namespace) -> dict[str, object]:
    service = _service_from_args(args)
    return service.build_plan().as_dict()


def _handle_export(args: argparse.Namespace) -> dict[str, object]:
    output_dir = Path(args.output_dir) if args.output_dir else None
    service = _service_from_args(args, output_dir=output_dir)
    result = service.export_rdf(
        output_dir=output_dir,
        max_active_rows_per_source=args.limit,
        include_attribute_relationships=args.include_attributes,
        include_snomed=not args.skip_snomed,
        include_map_refsets=not args.skip_map_refsets,
        include_mbs_schedule=not args.skip_mbs_schedule,
        include_phi_clinical_categories=not args.skip_phi_clinical_categories,
    )
    payload = result.as_dict()
    manifest_path = _manifest_path(args.manifest_path, result.output_files)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    payload["manifestPath"] = str(manifest_path)
    return payload


def _handle_load(args: argparse.Namespace) -> dict[str, object]:
    manifest = _read_manifest(args.manifest_path)
    graph_uris = _graph_uris_from_manifest(manifest, args.smoke_prefix)
    targets = _load_targets_from_manifest(manifest, graph_uris)
    summary = FusekiNTriplesBulkLoader(
        fuseki_url=args.fuseki_url,
        timeout_seconds=args.timeout_seconds,
    ).load_targets(targets, replace_existing_graphs=args.replace)
    return summary.as_dict()


def _handle_verify(args: argparse.Namespace) -> dict[str, object]:
    manifest = _read_manifest(args.manifest_path)
    graph_uris = _graph_uris_from_manifest(manifest, args.smoke_prefix)
    _set_fuseki_url(args.fuseki_url)
    expected_by_graph = _expected_lines_by_graph(manifest, graph_uris)
    graphs = {}
    for graph_uri, expected_lines in expected_by_graph.items():
        stored_triples = FusekiAdapter.get_named_graph_triple_count(graph_uri)
        graphs[graph_uri] = {
            "expectedLines": expected_lines,
            "storedTriples": stored_triples,
            "status": "present" if stored_triples > 0 else "missing",
        }
    return {"graphs": graphs}


def _handle_verify_integration(args: argparse.Namespace) -> dict[str, object]:
    _set_fuseki_url(args.fuseki_url)
    graph_uris = {
        "snomed": args.snomed_graph_uri,
        "snomedMapRefsets": args.map_refsets_graph_uri,
        "mbs": args.mbs_graph_uri,
    }
    graph_counts = {
        name: FusekiAdapter.get_named_graph_triple_count(graph_uri)
        for name, graph_uri in graph_uris.items()
    }
    timeout = max(1, int(args.timeout_seconds))
    mbs_item = _query_one(
        _mbs_item_query(args.mbs_graph_uri, args.mbs_item_number),
        timeout_seconds=timeout,
    )
    snomed_concept = _query_one(
        _snomed_concept_query(args.snomed_graph_uri, args.snomed_concept_id),
        timeout_seconds=timeout,
    )
    combined = _query_one(
        _combined_snomed_mbs_query(
            args.snomed_graph_uri,
            args.mbs_graph_uri,
            args.snomed_concept_id,
            args.mbs_item_number,
        ),
        timeout_seconds=timeout,
    )
    map_refsets = _map_refset_summary(
        args.map_refsets_graph_uri,
        timeout_seconds=timeout,
    )
    checks = {
        "graphsPresent": all(count > 0 for count in graph_counts.values()),
        "mbsItemResolvable": bool(mbs_item),
        "snomedConceptResolvable": bool(snomed_concept),
        "combinedGraphQueryResolvable": bool(combined),
        "mapRefsetsLoaded": map_refsets["simpleMapMemberCount"] > 0,
    }
    return {
        "status": "pass" if all(checks.values()) else "fail",
        "graphUris": graph_uris,
        "graphTripleCounts": graph_counts,
        "checks": checks,
        "mbsItem": _binding_values(mbs_item),
        "snomedConcept": _binding_values(snomed_concept),
        "combinedGraphQuery": _binding_values(combined),
        "mapRefsets": map_refsets,
    }


def _service_from_args(
    args: argparse.Namespace,
    *,
    output_dir: Path | None = None,
) -> SnomedMbsIngestionService:
    return SnomedMbsIngestionService(
        data_root=args.data_root,
        output_dir=output_dir,
        package_preference=args.package_preference,
        mbs_schedule_path=args.mbs_xml_path,
        mbs_schedule_url=args.mbs_xml_url,
        phi_clinical_categories_path=args.phi_clinical_categories_path,
        mbs_map_refset_ids=getattr(args, "mbs_map_refset_id", ()) or (),
    )


def _manifest_path(value: str | None, output_files: Mapping[str, Path]) -> Path:
    if value:
        return Path(value)
    if output_files:
        first_output = next(iter(output_files.values()))
        return Path(first_output).parent / DEFAULT_MANIFEST_NAME
    return Path(DEFAULT_MANIFEST_NAME)


def _read_manifest(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("export manifest must contain a JSON object")
    return data


def _graph_uris_from_manifest(
    manifest: Mapping[str, Any],
    smoke_prefix: str | None,
) -> dict[str, str]:
    if smoke_prefix:
        prefix = smoke_prefix.rstrip("/")
        return {
            "snomed": f"{prefix}/snomed",
            "snomedMapRefsets": f"{prefix}/map-refsets",
            "mbs": f"{prefix}/mbs",
        }
    graph_uris = manifest.get("graphUris")
    if not isinstance(graph_uris, dict):
        raise ValueError("export manifest is missing graphUris")
    return {str(key): str(value) for key, value in graph_uris.items()}


def _load_targets_from_manifest(
    manifest: Mapping[str, Any],
    graph_uris: Mapping[str, str],
) -> tuple[FusekiNTriplesLoadTarget, ...]:
    output_files = _mapping(manifest, "outputFiles")
    triple_counts = _mapping(manifest, "tripleCounts")
    targets: list[FusekiNTriplesLoadTarget] = []
    for role, path in output_files.items():
        graph_key = EXPORT_ROLE_GRAPH_KEYS.get(role)
        if graph_key is None:
            continue
        graph_uri = graph_uris[graph_key]
        count_value = triple_counts.get(role)
        targets.append(
            FusekiNTriplesLoadTarget(
                role=role,
                path=Path(path),
                graph_uri=graph_uri,
                triple_count=int(count_value) if count_value is not None else None,
            )
        )
    return tuple(targets)


def _expected_lines_by_graph(
    manifest: Mapping[str, Any],
    graph_uris: Mapping[str, str],
) -> dict[str, int]:
    triple_counts = _mapping(manifest, "tripleCounts")
    expected: dict[str, int] = {}
    for role, count in triple_counts.items():
        graph_key = EXPORT_ROLE_GRAPH_KEYS.get(role)
        if graph_key is None:
            continue
        graph_uri = graph_uris[graph_key]
        expected[graph_uri] = expected.get(graph_uri, 0) + int(count)
    return expected


def _mapping(manifest: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = manifest.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"export manifest is missing {key}")
    return {str(item_key): item_value for item_key, item_value in value.items()}


def _set_fuseki_url(url: str) -> None:
    fuseki_adapter.FUSEKI_URL = url.rstrip("/")


def _query_one(sparql: str, *, timeout_seconds: int) -> Mapping[str, Any]:
    rows = FusekiAdapter.execute_guarded_select(
        sparql,
        timeout_seconds=timeout_seconds,
    )
    return rows[0] if rows else {}


def _query_count(sparql: str, *, timeout_seconds: int) -> int:
    row = _query_one(sparql, timeout_seconds=timeout_seconds)
    return _binding_int(row.get("count"))


def _map_refset_summary(graph_uri: str, *, timeout_seconds: int) -> dict[str, object]:
    distribution_rows = FusekiAdapter.execute_guarded_select(
        _map_refset_distribution_query(graph_uri),
        timeout_seconds=timeout_seconds,
    )
    equivalent_class_count = _query_count(
        _equivalent_class_count_query(graph_uri),
        timeout_seconds=timeout_seconds,
    )
    return {
        "simpleMapMemberCount": _query_count(
            _map_refset_member_count_query(graph_uri),
            timeout_seconds=timeout_seconds,
        ),
        "equivalentClassCount": equivalent_class_count,
        "crosswalkStatus": (
            "available"
            if equivalent_class_count > 0
            else "not_configured"
        ),
        "refsetDistribution": [_binding_values(row) for row in distribution_rows],
    }


def _mbs_item_query(graph_uri: str, item_number: str) -> str:
    item_uri = f"http://mbsonline.gov.au/ontology/item/{_sparql_literal_segment(item_number)}"
    return f"""
PREFIX mbs: <http://mbsonline.gov.au/ontology/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?itemNumber ?fee ?categoryLabel ?procedureType WHERE {{
  GRAPH <{graph_uri}> {{
    <{item_uri}> mbs:itemNumber ?itemNumber .
    OPTIONAL {{ <{item_uri}> mbs:scheduleFee ?fee . }}
    OPTIONAL {{
      <{item_uri}> mbs:phiClinicalCategory ?category .
      ?category rdfs:label ?categoryLabel .
    }}
    OPTIONAL {{ <{item_uri}> mbs:phiProcedureType ?procedureType . }}
  }}
}} LIMIT 1
"""


def _snomed_concept_query(graph_uri: str, concept_id: str) -> str:
    concept_uri = f"http://snomed.info/id/{_sparql_literal_segment(concept_id)}"
    return f"""
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?label ?rootAncestor WHERE {{
  GRAPH <{graph_uri}> {{
    <{concept_uri}> rdfs:label ?label .
    OPTIONAL {{
      <{concept_uri}> rdfs:subClassOf+ ?rootAncestor .
      FILTER(?rootAncestor = <http://snomed.info/id/138875005>)
    }}
  }}
}} LIMIT 1
"""


def _combined_snomed_mbs_query(
    snomed_graph_uri: str,
    mbs_graph_uri: str,
    concept_id: str,
    item_number: str,
) -> str:
    concept_uri = f"http://snomed.info/id/{_sparql_literal_segment(concept_id)}"
    item_uri = f"http://mbsonline.gov.au/ontology/item/{_sparql_literal_segment(item_number)}"
    return f"""
PREFIX mbs: <http://mbsonline.gov.au/ontology/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?conceptLabel ?itemNumber ?fee WHERE {{
  GRAPH <{snomed_graph_uri}> {{
    <{concept_uri}> rdfs:label ?conceptLabel .
  }}
  GRAPH <{mbs_graph_uri}> {{
    <{item_uri}> mbs:itemNumber ?itemNumber .
    OPTIONAL {{ <{item_uri}> mbs:scheduleFee ?fee . }}
  }}
}} LIMIT 1
"""


def _map_refset_member_count_query(graph_uri: str) -> str:
    return f"""
PREFIX smbs: <http://inferra.ai/ontology/snomed-mbs#>
SELECT (COUNT(?member) AS ?count) WHERE {{
  GRAPH <{graph_uri}> {{ ?member a smbs:SimpleMapMember . }}
}}
"""


def _equivalent_class_count_query(graph_uri: str) -> str:
    return f"""
PREFIX owl: <http://www.w3.org/2002/07/owl#>
SELECT (COUNT(*) AS ?count) WHERE {{
  GRAPH <{graph_uri}> {{ ?s owl:equivalentClass ?o . }}
}}
"""


def _map_refset_distribution_query(graph_uri: str) -> str:
    return f"""
PREFIX smbs: <http://inferra.ai/ontology/snomed-mbs#>
SELECT ?refsetId (COUNT(?member) AS ?count) WHERE {{
  GRAPH <{graph_uri}> {{
    ?member a smbs:SimpleMapMember ;
      smbs:refsetId ?refsetId .
  }}
}} GROUP BY ?refsetId ORDER BY DESC(?count)
"""


def _binding_values(row: Mapping[str, Any]) -> dict[str, object]:
    values: dict[str, object] = {}
    for key, binding in row.items():
        if isinstance(binding, Mapping):
            values[str(key)] = binding.get("value")
        else:
            values[str(key)] = binding
    return values


def _binding_int(binding: Any) -> int:
    if not isinstance(binding, Mapping):
        return 0
    try:
        return int(str(binding.get("value", "0")))
    except (TypeError, ValueError):
        return 0


def _sparql_literal_segment(value: str) -> str:
    text = str(value)
    if any(char in text for char in '<>"{}|^`\\/?#[]@!$&\'()*+,;='):
        raise ValueError(f"SPARQL URI segment contains invalid characters: {value!r}")
    return text


if __name__ == "__main__":
    raise SystemExit(main())

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.tools import snomed_mbs_ops


def test_export_command_writes_manifest(tmp_path, capsys):
    output_file = tmp_path / "concepts.nt"
    output_file.write_text("<http://s> <http://p> <http://o> .\n", encoding="utf-8")

    class _ExportResult:
        output_files = {"concepts": output_file}

        def as_dict(self):
            return {
                "graphUris": {"snomed": "http://graph/snomed"},
                "outputFiles": {"concepts": str(output_file)},
                "tripleCounts": {"concepts": 1},
                "warnings": [],
            }

    service = MagicMock()
    service.export_rdf.return_value = _ExportResult()
    with patch.object(snomed_mbs_ops, "SnomedMbsIngestionService", return_value=service):
        assert snomed_mbs_ops.main(
            [
                "export",
                "--output-dir",
                str(tmp_path),
                "--limit",
                "2",
                "--include-attributes",
                "--skip-snomed",
            ]
        ) == 0

    service.export_rdf.assert_called_once()
    assert service.export_rdf.call_args.kwargs["max_active_rows_per_source"] == 2
    assert service.export_rdf.call_args.kwargs["include_attribute_relationships"] is True
    assert service.export_rdf.call_args.kwargs["include_snomed"] is False

    manifest_path = tmp_path / snomed_mbs_ops.DEFAULT_MANIFEST_NAME
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["tripleCounts"] == {"concepts": 1}

    output = json.loads(capsys.readouterr().out)
    assert output["manifestPath"] == str(manifest_path)


def test_load_command_uses_smoke_graph_prefix(tmp_path, capsys):
    manifest_path = _write_manifest(
        tmp_path,
        output_files={
            "concepts": str(tmp_path / "concepts.nt"),
            "mbs_items": str(tmp_path / "mbs.nt"),
        },
        triple_counts={"concepts": 2, "mbs_items": 3},
    )
    summary = SimpleNamespace(as_dict=lambda: {"totalTriples": 5})
    loader = MagicMock()
    loader.load_targets.return_value = summary

    with patch.object(snomed_mbs_ops, "FusekiNTriplesBulkLoader", return_value=loader):
        assert snomed_mbs_ops.main(
            [
                "load",
                "--manifest-path",
                str(manifest_path),
                "--smoke-prefix",
                "http://inferra.ai/ontology/smoke/test",
                "--replace",
            ]
        ) == 0

    targets = loader.load_targets.call_args.args[0]
    assert targets[0].graph_uri == "http://inferra.ai/ontology/smoke/test/snomed"
    assert targets[1].graph_uri == "http://inferra.ai/ontology/smoke/test/mbs"
    assert loader.load_targets.call_args.kwargs["replace_existing_graphs"] is True

    output = json.loads(capsys.readouterr().out)
    assert output == {"totalTriples": 5}


def test_verify_command_reports_expected_and_stored_counts(tmp_path, capsys):
    manifest_path = _write_manifest(
        tmp_path,
        output_files={
            "concepts": str(tmp_path / "concepts.nt"),
            "descriptions": str(tmp_path / "descriptions.nt"),
            "mbs_items": str(tmp_path / "mbs.nt"),
        },
        triple_counts={"concepts": 2, "descriptions": 4, "mbs_items": 3},
    )

    def _count(graph_uri):
        return {
            "http://inferra.ai/ontology/smoke/test/snomed": 6,
            "http://inferra.ai/ontology/smoke/test/mbs": 3,
        }[graph_uri]

    with patch.object(snomed_mbs_ops.FusekiAdapter, "get_named_graph_triple_count", side_effect=_count):
        assert snomed_mbs_ops.main(
            [
                "verify",
                "--manifest-path",
                str(manifest_path),
                "--smoke-prefix",
                "http://inferra.ai/ontology/smoke/test",
            ]
        ) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["graphs"]["http://inferra.ai/ontology/smoke/test/snomed"] == {
        "expectedLines": 6,
        "status": "present",
        "storedTriples": 6,
    }
    assert output["graphs"]["http://inferra.ai/ontology/smoke/test/mbs"] == {
        "expectedLines": 3,
        "status": "present",
        "storedTriples": 3,
    }


def test_verify_integration_reports_live_graph_readiness(capsys):
    def _count(graph_uri):
        return {
            "http://graph/snomed": 3183073,
            "http://graph/map-refsets": 495700,
            "http://graph/mbs": 181916,
        }[graph_uri]

    def _select(sparql, **_kwargs):
        if "GROUP BY ?refsetId" in sparql:
            return [
                {
                    "refsetId": {"value": "11000168105"},
                    "count": {"value": "51576"},
                }
            ]
        if "COUNT(?member)" in sparql:
            return [{"count": {"value": "99140"}}]
        if "owl:equivalentClass" in sparql:
            return [{"count": {"value": "0"}}]
        if "SELECT ?conceptLabel ?itemNumber ?fee" in sparql:
            return [
                {
                    "conceptLabel": {"value": "Procedure (procedure)"},
                    "itemNumber": {"value": "23"},
                    "fee": {"value": "45.05"},
                }
            ]
        if "SELECT ?label ?rootAncestor" in sparql:
            return [
                {
                    "label": {"value": "Procedure (procedure)"},
                    "rootAncestor": {"value": "http://snomed.info/id/138875005"},
                }
            ]
        if "SELECT ?itemNumber ?fee ?categoryLabel ?procedureType" in sparql:
            return [
                {
                    "itemNumber": {"value": "23"},
                    "fee": {"value": "45.05"},
                    "categoryLabel": {"value": "Common list"},
                    "procedureType": {"value": "Type C"},
                }
            ]
        raise AssertionError(f"Unexpected SPARQL: {sparql}")

    with patch.object(
        snomed_mbs_ops.FusekiAdapter,
        "get_named_graph_triple_count",
        side_effect=_count,
    ), patch.object(
        snomed_mbs_ops.FusekiAdapter,
        "execute_guarded_select",
        side_effect=_select,
    ):
        assert snomed_mbs_ops.main(
            [
                "verify-integration",
                "--fuseki-url",
                "http://localhost:3030/inferra",
                "--snomed-graph-uri",
                "http://graph/snomed",
                "--map-refsets-graph-uri",
                "http://graph/map-refsets",
                "--mbs-graph-uri",
                "http://graph/mbs",
            ]
        ) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "pass"
    assert output["checks"] == {
        "combinedGraphQueryResolvable": True,
        "graphsPresent": True,
        "mapRefsetsLoaded": True,
        "mbsItemResolvable": True,
        "snomedConceptResolvable": True,
    }
    assert output["mbsItem"]["fee"] == "45.05"
    assert output["snomedConcept"]["rootAncestor"] == "http://snomed.info/id/138875005"
    assert output["mapRefsets"]["crosswalkStatus"] == "not_configured"
    assert output["mapRefsets"]["equivalentClassCount"] == 0


def _write_manifest(
    tmp_path: Path,
    *,
    output_files: dict[str, str],
    triple_counts: dict[str, int],
) -> Path:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "graphUris": {
                    "snomed": "http://graph/snomed",
                    "snomedMapRefsets": "http://graph/map-refsets",
                    "mbs": "http://graph/mbs",
                },
                "outputFiles": output_files,
                "tripleCounts": triple_counts,
            }
        ),
        encoding="utf-8",
    )
    return manifest_path

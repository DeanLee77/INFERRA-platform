from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable

from src.adapters.outbound.ontology.fuseki_bulk_loader import FusekiNTriplesLoadTarget
from src.config import settings
from src.domain.snomed_mbs import (
    MbsXmlToRdfConverter,
    PhiClinicalCategoriesToRdfConverter,
    RdfTriple,
    Rf2ToRdfConverter,
    SnomedMbsReleaseManifest,
    discover_snomed_mbs_release,
)


EXPORT_ROLE_GRAPH_KEYS = {
    "concepts": "snomed",
    "descriptions": "snomed",
    "relationships": "snomed",
    "map_refsets": "snomedMapRefsets",
    "mbs_items": "mbs",
    "mbs_clinical_categories": "mbs",
}


@dataclass(frozen=True)
class SnomedMbsIngestionPlan:
    manifest: SnomedMbsReleaseManifest
    graph_uris: dict[str, str]
    output_dir: Path

    def as_dict(self) -> dict[str, object]:
        return {
            "manifest": self.manifest.as_dict(),
            "graphUris": dict(self.graph_uris),
            "outputDir": str(self.output_dir),
            "warnings": list(self.manifest.warnings),
        }


@dataclass(frozen=True)
class SnomedMbsRdfExportResult:
    manifest: SnomedMbsReleaseManifest
    graph_uris: dict[str, str]
    output_files: dict[str, Path]
    triple_counts: dict[str, int]
    max_active_rows_per_source: int | None
    include_attribute_relationships: bool
    include_snomed: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "manifest": self.manifest.as_dict(),
            "graphUris": dict(self.graph_uris),
            "outputFiles": {
                role: str(path) for role, path in self.output_files.items()
            },
            "tripleCounts": dict(self.triple_counts),
            "maxActiveRowsPerSource": self.max_active_rows_per_source,
            "includeAttributeRelationships": self.include_attribute_relationships,
            "includeSnomed": self.include_snomed,
            "warnings": list(self.manifest.warnings),
        }


class SnomedMbsIngestionService:
    """Prepare local SNOMED CT-AU RF2 and MBS reference data for Fuseki loading."""

    def __init__(
        self,
        *,
        data_root: str | Path | None = None,
        output_dir: str | Path | None = None,
        package_preference: str | None = None,
        mbs_schedule_path: str | Path | None = None,
        mbs_schedule_url: str | None = None,
        phi_clinical_categories_path: str | Path | None = None,
        mbs_map_refset_ids: Iterable[str] = (),
    ) -> None:
        self._data_root = Path(data_root or settings.SNOMED_MBS_DATA_ROOT)
        self._output_dir = Path(output_dir or settings.SNOMED_MBS_OUTPUT_DIR)
        self._package_preference = (
            package_preference or settings.SNOMED_MBS_PACKAGE_PREFERENCE
        )
        configured_mbs_path = mbs_schedule_path or settings.SNOMED_MBS_MBS_XML_PATH
        self._mbs_schedule_path = Path(configured_mbs_path) if configured_mbs_path else None
        self._mbs_schedule_url = mbs_schedule_url or settings.SNOMED_MBS_MBS_XML_URL
        configured_phi_path = (
            phi_clinical_categories_path
            or settings.SNOMED_MBS_PHI_CLINICAL_CATEGORIES_PATH
        )
        self._phi_clinical_categories_path = (
            Path(configured_phi_path) if configured_phi_path else None
        )
        self._mbs_map_refset_ids = tuple(str(value) for value in mbs_map_refset_ids)

    def discover_release(self) -> SnomedMbsReleaseManifest:
        return discover_snomed_mbs_release(
            self._data_root,
            package_preference=self._package_preference,
            mbs_schedule_url=self._mbs_schedule_url,
        )

    def build_plan(self) -> SnomedMbsIngestionPlan:
        manifest = self.discover_release()
        return SnomedMbsIngestionPlan(
            manifest=manifest,
            graph_uris=_graph_uris(
                manifest,
                mbs_schedule_path=self._resolve_mbs_schedule_path(manifest),
            ),
            output_dir=self._output_dir,
        )

    def export_rdf(
        self,
        *,
        output_dir: str | Path | None = None,
        max_active_rows_per_source: int | None = None,
        include_attribute_relationships: bool | None = None,
        include_snomed: bool = True,
        include_map_refsets: bool = True,
        include_mbs_schedule: bool = True,
        include_phi_clinical_categories: bool = True,
    ) -> SnomedMbsRdfExportResult:
        manifest = self.discover_release()
        target_dir = Path(output_dir or self._output_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        include_attributes = (
            settings.SNOMED_MBS_INCLUDE_ATTRIBUTE_RELATIONSHIPS
            if include_attribute_relationships is None
            else include_attribute_relationships
        )
        suffix = "preview" if max_active_rows_per_source is not None else "full"
        release_date = manifest.release_date

        output_files: dict[str, Path] = {}
        triple_counts: dict[str, int] = {}

        exports: list[tuple[str, Iterable[RdfTriple]]] = []
        if include_snomed or include_map_refsets:
            converter = Rf2ToRdfConverter(
                manifest,
                mbs_map_refset_ids=self._mbs_map_refset_ids,
            )
            if include_snomed:
                exports.extend(
                    [
                        (
                            "concepts",
                            converter.iter_concept_triples(
                                max_active_rows=max_active_rows_per_source
                            ),
                        ),
                        (
                            "descriptions",
                            converter.iter_description_triples(
                                max_active_rows=max_active_rows_per_source
                            ),
                        ),
                        (
                            "relationships",
                            converter.iter_relationship_triples(
                                include_attribute_relationships=include_attributes,
                                max_active_rows=max_active_rows_per_source,
                            ),
                        ),
                    ]
                )
            if include_map_refsets:
                exports.append(
                    (
                        "map_refsets",
                        converter.iter_map_refset_triples(
                            max_active_rows_per_file=max_active_rows_per_source
                        ),
                    ),
                )
        mbs_schedule_path = self._resolve_mbs_schedule_path(manifest)
        if include_mbs_schedule and mbs_schedule_path is not None:
            exports.append(
                (
                    "mbs_items",
                    MbsXmlToRdfConverter(mbs_schedule_path).iter_item_triples(
                        max_items=max_active_rows_per_source
                    ),
                )
            )
        phi_path = self._resolve_phi_clinical_categories_path(manifest)
        if include_phi_clinical_categories and phi_path is not None:
            exports.append(
                (
                    "mbs_clinical_categories",
                    PhiClinicalCategoriesToRdfConverter(phi_path).iter_category_triples(
                        max_rows_per_sheet=max_active_rows_per_source
                    ),
                )
            )

        for role, triples in exports:
            path = target_dir / f"snomed-ct-au-{release_date}-{role}.{suffix}.nt"
            count = _write_ntriples(path, triples)
            output_files[role] = path
            triple_counts[role] = count

        return SnomedMbsRdfExportResult(
            manifest=manifest,
            graph_uris=_graph_uris(manifest, mbs_schedule_path=mbs_schedule_path),
            output_files=output_files,
            triple_counts=triple_counts,
            max_active_rows_per_source=max_active_rows_per_source,
            include_attribute_relationships=include_attributes,
            include_snomed=include_snomed,
        )

    def build_fuseki_load_targets(
        self,
        export_result: SnomedMbsRdfExportResult,
    ) -> tuple[FusekiNTriplesLoadTarget, ...]:
        targets: list[FusekiNTriplesLoadTarget] = []
        for role, path in export_result.output_files.items():
            graph_key = _graph_key_for_export_role(role)
            if graph_key is None:
                continue
            graph_uri = export_result.graph_uris[graph_key]
            targets.append(
                FusekiNTriplesLoadTarget(
                    role=role,
                    path=path,
                    graph_uri=graph_uri,
                    triple_count=export_result.triple_counts.get(role),
                )
            )
        return tuple(targets)

    def _resolve_mbs_schedule_path(
        self,
        manifest: SnomedMbsReleaseManifest,
    ) -> Path | None:
        if self._mbs_schedule_path is not None:
            return self._mbs_schedule_path if self._mbs_schedule_path.is_file() else None
        return manifest.mbs_schedule_files[0] if manifest.mbs_schedule_files else None

    def _resolve_phi_clinical_categories_path(
        self,
        manifest: SnomedMbsReleaseManifest,
    ) -> Path | None:
        if self._phi_clinical_categories_path is not None:
            path = self._phi_clinical_categories_path
            return path if path.is_file() else None
        for path in manifest.auxiliary_healthcare_files:
            name = path.name.lower()
            if "clinical-category" in name or "clinical category" in name:
                return path
        return None


def _write_ntriples(path: Path, triples: Iterable[RdfTriple]) -> int:
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for triple in triples:
            handle.write(triple.to_ntriples())
            handle.write("\n")
            count += 1
    return count


def _graph_uris(
    manifest: SnomedMbsReleaseManifest,
    *,
    mbs_schedule_path: Path | None = None,
) -> dict[str, str]:
    release_date = manifest.release_date or "unknown"
    mbs_release_date = _mbs_release_date(
        manifest,
        mbs_schedule_path=mbs_schedule_path,
    )
    package = manifest.operational_package.lower()
    base = f"http://inferra.ai/ontology/snomed-ct-au/{release_date}"
    return {
        "snomed": f"{base}/{package}",
        "snomedMapRefsets": f"{base}/map-refsets",
        "mbs": f"http://inferra.ai/ontology/mbs/{mbs_release_date}",
    }


def _graph_key_for_export_role(role: str) -> str | None:
    return EXPORT_ROLE_GRAPH_KEYS.get(role)


def _mbs_release_date(
    manifest: SnomedMbsReleaseManifest,
    *,
    mbs_schedule_path: Path | None = None,
) -> str:
    values = [
        str(value)
        for value in (
            mbs_schedule_path,
            manifest.mbs_schedule_url,
            *(str(path) for path in manifest.mbs_schedule_files),
        )
        if value
    ]
    for value in values:
        match = re.search(r"MBS-XML-(20\d{6})", value, re.IGNORECASE)
        if match:
            return match.group(1)
    return manifest.release_date or "unknown"

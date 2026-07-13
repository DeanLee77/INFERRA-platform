from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Iterable, Mapping
from urllib.parse import quote

from src.domain.snomed_mbs.release import Rf2ReleaseFile, SnomedMbsReleaseManifest


SNOMED_NS = "http://snomed.info/id/"
MBS_NS = "http://mbsonline.gov.au/ontology/"
INF_SNOMED_MBS_NS = "http://inferra.ai/ontology/snomed-mbs#"

RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
RDFS_CLASS = "http://www.w3.org/2000/01/rdf-schema#Class"
RDFS_LABEL = "http://www.w3.org/2000/01/rdf-schema#label"
RDFS_SUBCLASS_OF = "http://www.w3.org/2000/01/rdf-schema#subClassOf"
SKOS_ALT_LABEL = "http://www.w3.org/2004/02/skos/core#altLabel"
OWL_EQUIVALENT_CLASS = "http://www.w3.org/2002/07/owl#equivalentClass"

SNOMED_IS_A = "116680003"
SNOMED_FSN = "900000000000003001"
SNOMED_SYNONYM = "900000000000013009"


def _raise_csv_field_limit() -> None:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit = limit // 10


_raise_csv_field_limit()


@dataclass(frozen=True)
class RdfObject:
    value: str
    is_uri: bool = True
    language: str | None = None
    datatype: str | None = None

    @classmethod
    def uri(cls, value: str) -> "RdfObject":
        return cls(value=value, is_uri=True)

    @classmethod
    def literal(
        cls,
        value: str,
        *,
        language: str | None = None,
        datatype: str | None = None,
    ) -> "RdfObject":
        return cls(value=value, is_uri=False, language=language, datatype=datatype)

    def to_ntriples(self) -> str:
        if self.is_uri:
            return f"<{_safe_uri(self.value)}>"
        escaped = _escape_literal(self.value)
        suffix = ""
        if self.language:
            suffix = f"@{self.language}"
        elif self.datatype:
            suffix = f"^^<{_safe_uri(self.datatype)}>"
        return f'"{escaped}"{suffix}'


@dataclass(frozen=True)
class RdfTriple:
    subject: str
    predicate: str
    obj: RdfObject
    source_role: str = ""

    def to_ntriples(self) -> str:
        return (
            f"<{_safe_uri(self.subject)}> "
            f"<{_safe_uri(self.predicate)}> "
            f"{self.obj.to_ntriples()} ."
        )


class Rf2ToRdfConverter:
    """Streaming RF2 to RDF converter for the SNOMED CT-AU subset INFERRA uses."""

    def __init__(
        self,
        manifest: SnomedMbsReleaseManifest,
        *,
        mbs_map_refset_ids: Iterable[str] = (),
    ) -> None:
        self._manifest = manifest
        self._mbs_map_refset_ids = {str(value) for value in mbs_map_refset_ids}

    def iter_concept_triples(
        self,
        *,
        max_active_rows: int | None = None,
    ) -> Iterable[RdfTriple]:
        file = self._manifest.concept_file
        if file is None:
            return
        emitted = 0
        for row in _iter_rf2_rows(file.path):
            if row.get("active") != "1":
                continue
            concept_uri = _snomed_uri(row["id"])
            yield RdfTriple(
                concept_uri,
                RDF_TYPE,
                RdfObject.uri(RDFS_CLASS),
                source_role=file.role,
            )
            emitted += 1
            if _limit_reached(emitted, max_active_rows):
                return

    def iter_description_triples(
        self,
        *,
        max_active_rows: int | None = None,
    ) -> Iterable[RdfTriple]:
        file = self._manifest.description_file
        if file is None:
            return
        emitted = 0
        for row in _iter_rf2_rows(file.path):
            if row.get("active") != "1":
                continue
            predicate = _description_predicate(row.get("typeId", ""))
            if predicate is None:
                continue
            concept_uri = _snomed_uri(row["conceptId"])
            yield RdfTriple(
                concept_uri,
                predicate,
                RdfObject.literal(row.get("term", ""), language="en-AU"),
                source_role=file.role,
            )
            emitted += 1
            if _limit_reached(emitted, max_active_rows):
                return

    def iter_relationship_triples(
        self,
        *,
        include_attribute_relationships: bool = False,
        max_active_rows: int | None = None,
    ) -> Iterable[RdfTriple]:
        file = self._manifest.relationship_file
        if file is None:
            return
        emitted = 0
        for row in _iter_rf2_rows(file.path):
            if row.get("active") != "1":
                continue
            source_uri = _snomed_uri(row["sourceId"])
            destination_uri = _snomed_uri(row["destinationId"])
            type_id = row.get("typeId", "")
            if type_id == SNOMED_IS_A:
                predicate = RDFS_SUBCLASS_OF
            elif include_attribute_relationships:
                predicate = _snomed_uri(type_id)
            else:
                continue
            yield RdfTriple(
                source_uri,
                predicate,
                RdfObject.uri(destination_uri),
                source_role=file.role,
            )
            emitted += 1
            if _limit_reached(emitted, max_active_rows):
                return

    def iter_map_refset_triples(
        self,
        *,
        max_active_rows_per_file: int | None = None,
    ) -> Iterable[RdfTriple]:
        for file in self._manifest.map_files:
            emitted = 0
            for row in _iter_rf2_rows(file.path):
                if row.get("active") != "1":
                    continue
                if "mapTarget" not in row or "referencedComponentId" not in row:
                    continue
                yield from self._map_membership_triples(file, row)
                emitted += 1
                if _limit_reached(emitted, max_active_rows_per_file):
                    break

    def _map_membership_triples(
        self,
        file: Rf2ReleaseFile,
        row: Mapping[str, str],
    ) -> Iterable[RdfTriple]:
        member_uri = f"{INF_SNOMED_MBS_NS}rf2-member/{quote(row['id'], safe='')}"
        component_uri = _snomed_uri(row["referencedComponentId"])
        refset_id = row.get("refsetId", "")
        map_target = row.get("mapTarget", "")

        yield RdfTriple(
            member_uri,
            RDF_TYPE,
            RdfObject.uri(f"{INF_SNOMED_MBS_NS}SimpleMapMember"),
            source_role=file.role,
        )
        yield RdfTriple(
            member_uri,
            f"{INF_SNOMED_MBS_NS}refsetId",
            RdfObject.literal(refset_id),
            source_role=file.role,
        )
        yield RdfTriple(
            member_uri,
            f"{INF_SNOMED_MBS_NS}referencedComponent",
            RdfObject.uri(component_uri),
            source_role=file.role,
        )
        yield RdfTriple(
            member_uri,
            f"{INF_SNOMED_MBS_NS}mapTarget",
            RdfObject.literal(map_target),
            source_role=file.role,
        )
        yield RdfTriple(
            component_uri,
            f"{INF_SNOMED_MBS_NS}hasMapMembership",
            RdfObject.uri(member_uri),
            source_role=file.role,
        )

        if refset_id in self._mbs_map_refset_ids and map_target:
            mbs_uri = _mbs_item_uri(map_target)
            yield RdfTriple(
                mbs_uri,
                OWL_EQUIVALENT_CLASS,
                RdfObject.uri(component_uri),
                source_role=file.role,
            )


def _iter_rf2_rows(path: Path) -> Iterable[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            yield {key: value for key, value in row.items() if key is not None}


def _description_predicate(type_id: str) -> str | None:
    if type_id == SNOMED_FSN:
        return RDFS_LABEL
    if type_id == SNOMED_SYNONYM:
        return SKOS_ALT_LABEL
    return None


def _snomed_uri(concept_id: str) -> str:
    return f"{SNOMED_NS}{concept_id}"


def _mbs_item_uri(item_number: str) -> str:
    return f"{MBS_NS}item/{quote(item_number, safe='')}"


def _limit_reached(emitted: int, limit: int | None) -> bool:
    return limit is not None and emitted >= limit


def _safe_uri(value: str) -> str:
    if any(char in value for char in '<>"{}|^`\\'):
        raise ValueError(f"Invalid URI value: {value!r}")
    return value


def _escape_literal(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )

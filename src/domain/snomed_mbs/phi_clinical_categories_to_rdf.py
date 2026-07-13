from __future__ import annotations

from pathlib import Path
import re
import xml.etree.ElementTree as ET
from typing import Iterable
from urllib.parse import quote
from zipfile import ZipFile

from src.domain.snomed_mbs.mbs_xml_to_rdf import XSD_DATE
from src.domain.snomed_mbs.rf2_to_rdf import (
    MBS_NS,
    RDF_TYPE,
    RDFS_LABEL,
    RdfObject,
    RdfTriple,
)


RDFS_COMMENT = "http://www.w3.org/2000/01/rdf-schema#comment"
PHI_CLINICAL_CATEGORY_CLASS = f"{MBS_NS}PHIClinicalCategory"
PHI_DELETED_ITEM_CLASS = f"{MBS_NS}PHIDeletedMBSItem"
NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}


class PhiClinicalCategoriesToRdfConverter:
    """Convert the PHI clinical-category workbook into MBS enrichment triples."""

    def __init__(self, workbook_path: str | Path) -> None:
        self._workbook = _XlsxWorkbook(Path(workbook_path))

    def iter_category_triples(
        self,
        *,
        max_rows_per_sheet: int | None = None,
    ) -> Iterable[RdfTriple]:
        yield from self._iter_classification_triples(max_rows_per_sheet)
        yield from self._iter_definition_triples(max_rows_per_sheet)
        yield from self._iter_deleted_item_triples(max_rows_per_sheet)

    def _iter_classification_triples(
        self,
        max_rows: int | None,
    ) -> Iterable[RdfTriple]:
        for row in self._iter_dict_rows("PHI Classifications", max_rows=max_rows):
            item_number = row.get("MBS Item", "").strip()
            clinical_category = row.get("Clinical Category", "").strip()
            procedure_type = row.get("Procedure Type", "").strip()
            new_item = row.get("New Item", "").strip()
            if not item_number or not clinical_category:
                continue

            item_uri = _mbs_item_uri(item_number)
            category_uri = _category_uri(clinical_category)
            yield RdfTriple(
                item_uri,
                _mbs_predicate("phiClinicalCategory"),
                RdfObject.uri(category_uri),
                "phi_classification",
            )
            yield RdfTriple(
                category_uri,
                RDF_TYPE,
                RdfObject.uri(PHI_CLINICAL_CATEGORY_CLASS),
                "phi_classification",
            )
            yield RdfTriple(
                category_uri,
                RDFS_LABEL,
                RdfObject.literal(clinical_category, language="en-AU"),
                "phi_classification",
            )
            if procedure_type:
                yield RdfTriple(
                    item_uri,
                    _mbs_predicate("phiProcedureType"),
                    RdfObject.literal(procedure_type),
                    "phi_classification",
                )
            if new_item:
                yield RdfTriple(
                    item_uri,
                    _mbs_predicate("phiNewItemFlag"),
                    RdfObject.literal(new_item),
                    "phi_classification",
                )

    def _iter_definition_triples(
        self,
        max_rows: int | None,
    ) -> Iterable[RdfTriple]:
        for row in self._iter_dict_rows("PHI Definitions", max_rows=max_rows):
            category = row.get("Clinical Category", "").strip()
            scope = row.get("Scope of cover", "").strip()
            treatment = row.get("Treatment that must be covered", "").strip()
            if not category:
                continue
            category_uri = _category_uri(category)
            yield RdfTriple(
                category_uri,
                RDF_TYPE,
                RdfObject.uri(PHI_CLINICAL_CATEGORY_CLASS),
                "phi_definition",
            )
            yield RdfTriple(
                category_uri,
                RDFS_LABEL,
                RdfObject.literal(category, language="en-AU"),
                "phi_definition",
            )
            if scope:
                yield RdfTriple(
                    category_uri,
                    _mbs_predicate("phiScopeOfCover"),
                    RdfObject.literal(_clean_text(scope), language="en-AU"),
                    "phi_definition",
                )
            if treatment:
                yield RdfTriple(
                    category_uri,
                    RDFS_COMMENT,
                    RdfObject.literal(_clean_text(treatment), language="en-AU"),
                    "phi_definition",
                )
                for item_number in _extract_mbs_item_numbers(treatment):
                    yield RdfTriple(
                        category_uri,
                        _mbs_predicate("phiMustCoverMbsItem"),
                        RdfObject.uri(_mbs_item_uri(item_number)),
                        "phi_definition",
                    )

    def _iter_deleted_item_triples(
        self,
        max_rows: int | None,
    ) -> Iterable[RdfTriple]:
        for row in self._iter_dict_rows("Deleted items list", max_rows=max_rows):
            item_number = row.get("MBS Item", "").strip()
            deletion_date = _excel_or_text_date(row.get("Date of Deletion", "").strip())
            if not item_number:
                continue
            item_uri = _mbs_item_uri(item_number)
            yield RdfTriple(
                item_uri,
                RDF_TYPE,
                RdfObject.uri(PHI_DELETED_ITEM_CLASS),
                "phi_deleted_item",
            )
            if deletion_date:
                yield RdfTriple(
                    item_uri,
                    _mbs_predicate("phiDeletionDate"),
                    RdfObject.literal(deletion_date, datatype=XSD_DATE),
                    "phi_deleted_item",
                )

    def _iter_dict_rows(
        self,
        sheet_name: str,
        *,
        max_rows: int | None,
    ) -> Iterable[dict[str, str]]:
        rows = self._workbook.iter_rows(sheet_name)
        headers = next(rows, [])
        normalized_headers = [_normalize_header(value) for value in headers]
        emitted = 0
        for row in rows:
            values = {
                header: row[index].strip() if index < len(row) else ""
                for index, header in enumerate(normalized_headers)
                if header
            }
            if any(values.values()):
                yield values
                emitted += 1
            if max_rows is not None and emitted >= max_rows:
                return


class _XlsxWorkbook:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._zip = ZipFile(path)
        self._shared_strings = self._load_shared_strings()
        self._sheet_paths = self._load_sheet_paths()

    def iter_rows(self, sheet_name: str) -> Iterable[list[str]]:
        path = self._sheet_paths.get(sheet_name)
        if path is None:
            return iter(())
        root = ET.fromstring(self._zip.read(path))
        return (_read_row(row, self._shared_strings) for row in root.findall("m:sheetData/m:row", NS))

    def _load_shared_strings(self) -> list[str]:
        if "xl/sharedStrings.xml" not in self._zip.namelist():
            return []
        root = ET.fromstring(self._zip.read("xl/sharedStrings.xml"))
        return [
            "".join(text.text or "" for text in item.findall(".//m:t", NS))
            for item in root.findall("m:si", NS)
        ]

    def _load_sheet_paths(self) -> dict[str, str]:
        rels = ET.fromstring(self._zip.read("xl/_rels/workbook.xml.rels"))
        rel_by_id = {
            rel.attrib["Id"]: _xl_path(rel.attrib["Target"])
            for rel in rels.findall("rel:Relationship", NS)
        }
        workbook = ET.fromstring(self._zip.read("xl/workbook.xml"))
        sheets: dict[str, str] = {}
        for sheet in workbook.findall("m:sheets/m:sheet", NS):
            name = sheet.attrib["name"]
            rel_id = sheet.attrib[
                "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
            ]
            if rel_id in rel_by_id:
                sheets[name] = rel_by_id[rel_id]
        return sheets


def _read_row(row: ET.Element, shared_strings: list[str]) -> list[str]:
    values: list[str] = []
    for cell in row.findall("m:c", NS):
        column_index = _column_index(cell.attrib.get("r", "A1"))
        while len(values) < column_index - 1:
            values.append("")
        values.append(_cell_value(cell, shared_strings))
    return values


def _cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t", "")
    if cell_type == "inlineStr":
        return "".join(text.text or "" for text in cell.findall(".//m:t", NS)).strip()
    value = cell.find("m:v", NS)
    if value is None or value.text is None:
        return ""
    raw = value.text.strip()
    if cell_type == "s" and raw:
        return shared_strings[int(raw)].strip()
    return raw


def _xl_path(target: str) -> str:
    return target if target.startswith("xl/") else f"xl/{target.lstrip('/')}"


def _column_index(cell_ref: str) -> int:
    match = re.match(r"([A-Z]+)", cell_ref)
    if not match:
        return 1
    index = 0
    for char in match.group(1):
        index = index * 26 + ord(char) - 64
    return index


def _normalize_header(value: str) -> str:
    normalized = _clean_text(value).strip(": ")
    aliases = {
        "Clinical Category": "Clinical Category",
        "Scope of cover": "Scope of cover",
        "Treatment that must be covered": "Treatment that must be covered",
        "MBS Item": "MBS Item",
        "Date of Deletion": "Date of Deletion",
        "Procedure Type": "Procedure Type",
        "New Item": "New Item",
    }
    return aliases.get(normalized, normalized)


def _extract_mbs_item_numbers(value: str) -> tuple[str, ...]:
    if "No items listed" in value:
        return ()
    return tuple(dict.fromkeys(re.findall(r"\b\d{2,6}\b", value)))


def _excel_or_text_date(value: str) -> str:
    if not value:
        return ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return value
    match = re.fullmatch(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", value)
    if match:
        day, month, year = match.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"
    if re.fullmatch(r"\d+(\.\d+)?", value):
        serial = int(float(value))
        # Excel incorrectly treats 1900 as a leap year; serial 60 is skipped here.
        from datetime import date, timedelta

        return (date(1899, 12, 30) + timedelta(days=serial)).isoformat()
    return value


def _category_uri(category: str) -> str:
    return f"{MBS_NS}phi-clinical-category/{quote(_slug(category), safe='')}"


def _mbs_item_uri(item_number: str) -> str:
    return f"{MBS_NS}item/{quote(item_number, safe='')}"


def _mbs_predicate(name: str) -> str:
    return f"{MBS_NS}{name}"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()

from __future__ import annotations

from pathlib import Path
import re
import xml.etree.ElementTree as ET
from typing import Iterable
from urllib.parse import quote

from src.domain.snomed_mbs.rf2_to_rdf import (
    MBS_NS,
    RDF_TYPE,
    RDFS_LABEL,
    RdfObject,
    RdfTriple,
)


RDFS_COMMENT = "http://www.w3.org/2000/01/rdf-schema#comment"
XSD_DATE = "http://www.w3.org/2001/XMLSchema#date"
XSD_DECIMAL = "http://www.w3.org/2001/XMLSchema#decimal"
MBS_ITEM_CLASS = f"{MBS_NS}MBSItem"
MBS_GROUP_CLASS = f"{MBS_NS}MBSGroup"
MBS_SUBGROUP_CLASS = f"{MBS_NS}MBSSubGroup"

TEXT_FIELDS = {
    "SubItemNum": "subItemNumber",
    "Category": "category",
    "Group": "group",
    "SubGroup": "subGroup",
    "SubHeading": "subHeading",
    "ItemType": "itemType",
    "FeeType": "feeType",
    "ProviderType": "providerType",
    "NewItem": "newItemFlag",
    "ItemChange": "itemChangeFlag",
    "AnaesChange": "anaesChangeFlag",
    "DescriptorChange": "descriptorChangeFlag",
    "FeeChange": "feeChangeFlag",
    "EMSNChange": "emsnChangeFlag",
    "EMSNCap": "emsnCapType",
    "BenefitType": "benefitType",
    "BasicUnits": "basicUnits",
    "EMSNDescription": "emsnDescription",
    "DerivedFee": "derivedFeeText",
    "Anaes": "anaes",
}
DATE_FIELDS = {
    "ItemStartDate": "itemStartDate",
    "ItemEndDate": "itemEndDate",
    "BenefitStartDate": "benefitStartDate",
    "FeeStartDate": "feeStartDate",
    "EMSNStartDate": "emsnStartDate",
    "EMSNEndDate": "emsnEndDate",
    "EMSNChangeDate": "emsnChangeDate",
    "DescriptionStartDate": "descriptionStartDate",
    "QFEStartDate": "qfeStartDate",
    "QFEEndDate": "qfeEndDate",
    "DerivedFeeStartDate": "derivedFeeStartDate",
}
DECIMAL_FIELDS = {
    "ScheduleFee": "scheduleFee",
    "Benefit75": "benefit75",
    "Benefit85": "benefit85",
    "Benefit100": "benefit100",
    "EMSNFixedCapAmount": "emsnFixedCapAmount",
    "EMSNMaximumCap": "emsnMaximumCap",
    "EMSNPercentageCap": "emsnPercentageCap",
}


class MbsXmlToRdfConverter:
    """Streaming MBS Online XML to RDF converter."""

    def __init__(self, xml_path: str | Path) -> None:
        self._xml_path = Path(xml_path)

    def iter_item_triples(
        self,
        *,
        max_items: int | None = None,
    ) -> Iterable[RdfTriple]:
        emitted = 0
        for item in _iter_mbs_items(self._xml_path):
            item_number = item.get("ItemNum", "")
            if not item_number:
                continue
            yield from _item_triples(item)
            emitted += 1
            if max_items is not None and emitted >= max_items:
                return


def _iter_mbs_items(path: Path) -> Iterable[dict[str, str]]:
    for _event, elem in ET.iterparse(path, events=("end",)):
        if _local_name(elem.tag) != "Data":
            continue
        item = {
            _local_name(child.tag): (child.text or "").strip()
            for child in list(elem)
        }
        yield item
        elem.clear()


def _item_triples(item: dict[str, str]) -> Iterable[RdfTriple]:
    item_number = item["ItemNum"]
    item_uri = _mbs_item_uri(item_number)

    yield RdfTriple(item_uri, RDF_TYPE, RdfObject.uri(MBS_ITEM_CLASS), "mbs_item")
    yield RdfTriple(
        item_uri,
        RDFS_LABEL,
        RdfObject.literal(f"MBS item {item_number}", language="en-AU"),
        "mbs_item",
    )
    yield RdfTriple(
        item_uri,
        _mbs_predicate("itemNumber"),
        RdfObject.literal(item_number),
        "mbs_item",
    )

    description = _clean_text(item.get("Description", ""))
    if description:
        yield RdfTriple(
            item_uri,
            RDFS_COMMENT,
            RdfObject.literal(description, language="en-AU"),
            "mbs_item",
        )

    for xml_name, predicate_name in TEXT_FIELDS.items():
        value = _clean_text(item.get(xml_name, ""))
        if value:
            yield RdfTriple(
                item_uri,
                _mbs_predicate(predicate_name),
                RdfObject.literal(value),
                "mbs_item",
            )

    for xml_name, predicate_name in DATE_FIELDS.items():
        value = _to_iso_date(item.get(xml_name, ""))
        if value:
            yield RdfTriple(
                item_uri,
                _mbs_predicate(predicate_name),
                RdfObject.literal(value, datatype=XSD_DATE),
                "mbs_item",
            )

    for xml_name, predicate_name in DECIMAL_FIELDS.items():
        value = _decimal_value(item.get(xml_name, ""))
        if value:
            yield RdfTriple(
                item_uri,
                _mbs_predicate(predicate_name),
                RdfObject.literal(value, datatype=XSD_DECIMAL),
                "mbs_item",
            )

    group = item.get("Group", "").strip()
    subgroup = item.get("SubGroup", "").strip()
    if group:
        group_uri = _mbs_group_uri(group)
        yield RdfTriple(
            item_uri,
            _mbs_predicate("inGroup"),
            RdfObject.uri(group_uri),
            "mbs_item",
        )
        yield RdfTriple(
            group_uri,
            RDF_TYPE,
            RdfObject.uri(MBS_GROUP_CLASS),
            "mbs_group",
        )
        yield RdfTriple(
            group_uri,
            RDFS_LABEL,
            RdfObject.literal(f"MBS group {group}", language="en-AU"),
            "mbs_group",
        )
    if group and subgroup:
        subgroup_uri = _mbs_subgroup_uri(group, subgroup)
        yield RdfTriple(
            item_uri,
            _mbs_predicate("inSubGroup"),
            RdfObject.uri(subgroup_uri),
            "mbs_item",
        )
        yield RdfTriple(
            subgroup_uri,
            RDF_TYPE,
            RdfObject.uri(MBS_SUBGROUP_CLASS),
            "mbs_subgroup",
        )
        yield RdfTriple(
            subgroup_uri,
            RDFS_LABEL,
            RdfObject.literal(
                f"MBS group {group} subgroup {subgroup}",
                language="en-AU",
            ),
            "mbs_subgroup",
        )
        yield RdfTriple(
            subgroup_uri,
            _mbs_predicate("parentGroup"),
            RdfObject.uri(_mbs_group_uri(group)),
            "mbs_subgroup",
        )


def _mbs_item_uri(item_number: str) -> str:
    return f"{MBS_NS}item/{quote(item_number, safe='')}"


def _mbs_group_uri(group: str) -> str:
    return f"{MBS_NS}group/{quote(group, safe='')}"


def _mbs_subgroup_uri(group: str, subgroup: str) -> str:
    return f"{MBS_NS}group/{quote(group, safe='')}/subgroup/{quote(subgroup, safe='')}"


def _mbs_predicate(name: str) -> str:
    return f"{MBS_NS}{name}"


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _to_iso_date(value: str) -> str:
    raw = value.strip()
    if not raw:
        return ""
    match = re.fullmatch(r"(\d{2})\.(\d{2})\.(\d{4})", raw)
    if not match:
        return raw
    day, month, year = match.groups()
    return f"{year}-{month}-{day}"


def _decimal_value(value: str) -> str:
    raw = value.strip().replace(",", "")
    if not raw:
        return ""
    return raw if re.fullmatch(r"-?\d+(\.\d+)?", raw) else ""

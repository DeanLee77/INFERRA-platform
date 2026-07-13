from pathlib import Path
from zipfile import ZipFile

from src.domain.snomed_mbs import discover_snomed_mbs_release
from src.services.snomed_mbs_ingestion_service import SnomedMbsIngestionService


def test_release_discovery_uses_snapshot_when_all_package_has_no_delta(tmp_path):
    data_root = _make_rf2_release(tmp_path)

    manifest = discover_snomed_mbs_release(
        data_root,
        package_preference="Delta",
    )

    assert manifest.package_type == "ALL"
    assert manifest.operational_package == "Snapshot"
    assert manifest.has_snapshot is True
    assert manifest.has_full is True
    assert manifest.has_delta is False
    assert manifest.current_rf2_files_present is True
    assert manifest.mbs_schedule_files
    assert manifest.mbs_schedule_url.endswith("MBS-XML-20260701.XML")
    assert any("Delta package is not present" in item for item in manifest.warnings)
    assert any("falling back to Snapshot" in item for item in manifest.warnings)


def test_export_rdf_streams_active_snapshot_rows_to_ntriples(tmp_path):
    data_root = _make_rf2_release(tmp_path)
    output_dir = tmp_path / "out"

    result = SnomedMbsIngestionService(
        data_root=data_root,
        output_dir=output_dir,
    ).export_rdf(
        max_active_rows_per_source=10,
        include_attribute_relationships=True,
    )

    assert result.triple_counts["concepts"] == 2
    assert result.triple_counts["descriptions"] == 2
    assert result.triple_counts["relationships"] == 2
    assert result.triple_counts["map_refsets"] == 5
    assert result.triple_counts["mbs_items"] > 20
    assert result.triple_counts["mbs_clinical_categories"] > 15
    assert result.graph_uris["snomed"].endswith("/20260630/snapshot")

    concept_lines = _read_lines(result.output_files["concepts"])
    description_lines = _read_lines(result.output_files["descriptions"])
    relationship_lines = _read_lines(result.output_files["relationships"])
    map_lines = _read_lines(result.output_files["map_refsets"])
    mbs_lines = _read_lines(result.output_files["mbs_items"])
    phi_lines = _read_lines(result.output_files["mbs_clinical_categories"])

    assert (
        "<http://snomed.info/id/100001> "
        "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type> "
        "<http://www.w3.org/2000/01/rdf-schema#Class> ."
    ) in concept_lines
    assert not any("100003" in line for line in concept_lines)
    assert any('"Example procedure (procedure)"@en-AU' in line for line in description_lines)
    assert any("skos/core#altLabel" in line for line in description_lines)
    assert any("rdf-schema#subClassOf" in line for line in relationship_lines)
    assert any("<http://snomed.info/id/363704007>" in line for line in relationship_lines)
    assert any("mapTarget" in line and '"23"' in line for line in map_lines)
    assert any("<http://mbsonline.gov.au/ontology/item/23>" in line for line in mbs_lines)
    assert any("scheduleFee" in line and '"45.05"' in line for line in mbs_lines)
    assert any('"2026-07-01"^^<http://www.w3.org/2001/XMLSchema#date>' in line for line in mbs_lines)
    assert any("phiClinicalCategory" in line for line in phi_lines)
    assert any("phiProcedureType" in line and '"Type C"' in line for line in phi_lines)
    assert any("phiMustCoverMbsItem" in line and "/item/170>" in line for line in phi_lines)
    assert any("phiDeletionDate" in line and '"2026-07-01"' in line for line in phi_lines)

    targets = SnomedMbsIngestionService(
        data_root=data_root,
        output_dir=output_dir,
    ).build_fuseki_load_targets(result)
    targets_by_role = {target.role: target for target in targets}
    assert result.graph_uris["mbs"].endswith("/20260701")
    assert targets_by_role["concepts"].graph_uri == result.graph_uris["snomed"]
    assert targets_by_role["descriptions"].graph_uri == result.graph_uris["snomed"]
    assert targets_by_role["relationships"].graph_uri == result.graph_uris["snomed"]
    assert targets_by_role["map_refsets"].graph_uri == result.graph_uris["snomedMapRefsets"]
    assert targets_by_role["mbs_items"].graph_uri == result.graph_uris["mbs"]
    assert targets_by_role["mbs_clinical_categories"].graph_uri == result.graph_uris["mbs"]


def test_export_rdf_can_export_mbs_and_phi_without_snomed(tmp_path):
    data_root = _make_rf2_release(tmp_path)

    result = SnomedMbsIngestionService(
        data_root=data_root,
        output_dir=tmp_path / "out",
    ).export_rdf(
        max_active_rows_per_source=10,
        include_snomed=False,
        include_map_refsets=False,
    )

    assert set(result.output_files) == {"mbs_items", "mbs_clinical_categories"}
    assert set(result.triple_counts) == {"mbs_items", "mbs_clinical_categories"}
    assert result.as_dict()["includeSnomed"] is False
    assert result.graph_uris["mbs"] == "http://inferra.ai/ontology/mbs/20260701"

    targets = SnomedMbsIngestionService(
        data_root=data_root,
        output_dir=tmp_path / "out",
    ).build_fuseki_load_targets(result)

    assert {target.role for target in targets} == {
        "mbs_items",
        "mbs_clinical_categories",
    }
    assert {target.graph_uri for target in targets} == {result.graph_uris["mbs"]}


def test_export_rdf_handles_large_rf2_description_fields(tmp_path):
    data_root = _make_rf2_release(tmp_path)
    description_path = next(data_root.rglob("sct2_Description_Snapshot-*.txt"))
    large_term = "Large RF2 description " + ("x" * 150_000)
    with description_path.open("a", encoding="utf-8", newline="") as handle:
        handle.write(
            "200004\t20260630\t1\t32506021000036107\t100002\ten\t"
            f"900000000000013009\t{large_term}\t900000000000017005\n"
        )

    result = SnomedMbsIngestionService(
        data_root=data_root,
        output_dir=tmp_path / "out",
    ).export_rdf(
        include_map_refsets=False,
        include_mbs_schedule=False,
        include_phi_clinical_categories=False,
    )

    assert result.triple_counts["descriptions"] == 3
    assert any(
        large_term in line
        for line in _read_lines(result.output_files["descriptions"])
    )


def test_configured_mbs_map_refset_adds_equivalent_class_crosswalk(tmp_path):
    data_root = _make_rf2_release(tmp_path)

    result = SnomedMbsIngestionService(
        data_root=data_root,
        output_dir=tmp_path / "out",
        mbs_map_refset_ids=("999000",),
    ).export_rdf(max_active_rows_per_source=10)

    map_lines = _read_lines(result.output_files["map_refsets"])

    assert result.triple_counts["map_refsets"] == 6
    assert any(
        "<http://mbsonline.gov.au/ontology/item/23> "
        "<http://www.w3.org/2002/07/owl#equivalentClass> "
        "<http://snomed.info/id/100001> ."
        in line
        for line in map_lines
    )


def _make_rf2_release(tmp_path: Path) -> Path:
    data_root = tmp_path / "data"
    release_root = data_root / "SnomedCT_Release_AU1000036_20260630"
    snapshot = release_root / "Snapshot"
    full = release_root / "Full"
    (snapshot / "Terminology").mkdir(parents=True)
    (snapshot / "Refset" / "Map").mkdir(parents=True)
    (full / "Terminology").mkdir(parents=True)

    _write(
        snapshot / "Terminology" / "sct2_Concept_Snapshot_AU1000036_20260630.txt",
        [
            "id\teffectiveTime\tactive\tmoduleId\tdefinitionStatusId",
            "100001\t20260630\t1\t32506021000036107\t900000000000074008",
            "100002\t20260630\t1\t32506021000036107\t900000000000074008",
            "100003\t20260630\t0\t32506021000036107\t900000000000074008",
        ],
    )
    _write(
        snapshot
        / "Terminology"
        / "sct2_Description_Snapshot-en-au_AU1000036_20260630.txt",
        [
            "id\teffectiveTime\tactive\tmoduleId\tconceptId\tlanguageCode\ttypeId\tterm\tcaseSignificanceId",
            "200001\t20260630\t1\t32506021000036107\t100001\ten\t900000000000003001\tExample procedure (procedure)\t900000000000017005",
            "200002\t20260630\t1\t32506021000036107\t100001\ten\t900000000000013009\tExample procedure\t900000000000017005",
            "200003\t20260630\t0\t32506021000036107\t100001\ten\t900000000000013009\tInactive description\t900000000000017005",
        ],
    )
    _write(
        snapshot
        / "Terminology"
        / "sct2_Relationship_Snapshot_AU1000036_20260630.txt",
        [
            "id\teffectiveTime\tactive\tmoduleId\tsourceId\tdestinationId\trelationshipGroup\ttypeId\tcharacteristicTypeId\tmodifierId",
            "300001\t20260630\t1\t32506021000036107\t100001\t100002\t0\t116680003\t900000000000011006\t900000000000451002",
            "300002\t20260630\t1\t32506021000036107\t100001\t123037004\t0\t363704007\t900000000000011006\t900000000000451002",
            "300003\t20260630\t0\t32506021000036107\t100001\t404684003\t0\t116680003\t900000000000011006\t900000000000451002",
        ],
    )
    _write(
        snapshot / "Refset" / "Map" / "der2_iRefset_SimpleMapSnapshot_AU1000036_20260630.txt",
        [
            "id\teffectiveTime\tactive\tmoduleId\trefsetId\treferencedComponentId\tmapTarget",
            "400001\t20260630\t1\t32506021000036107\t999000\t100001\t23",
            "400002\t20260630\t0\t32506021000036107\t999000\t100002\t36",
        ],
    )
    _write(
        full / "Terminology" / "sct2_Concept_Full_AU1000036_20260630.txt",
        [
            "id\teffectiveTime\tactive\tmoduleId\tdefinitionStatusId",
            "100001\t20260630\t1\t32506021000036107\t900000000000074008",
        ],
    )
    _write_phi_workbook(
        release_root
        / "private-health-insurance-clinical-category-classification-and-definitions-1-july-2026_0.xlsx"
    )
    _write(
        data_root / "MBS-XML-20260701.XML",
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            "<MBS_XML>",
            "<Data>",
            "<ItemNum>23</ItemNum>",
            "<SubItemNum></SubItemNum>",
            "<ItemStartDate>01.12.1989</ItemStartDate>",
            "<ItemEndDate></ItemEndDate>",
            "<Category>1</Category>",
            "<Group>A1</Group>",
            "<SubGroup></SubGroup>",
            "<SubHeading>2</SubHeading>",
            "<ItemType>S</ItemType>",
            "<FeeType>N</FeeType>",
            "<ProviderType></ProviderType>",
            "<NewItem>N</NewItem>",
            "<ItemChange>Y</ItemChange>",
            "<AnaesChange>N</AnaesChange>",
            "<DescriptorChange>N</DescriptorChange>",
            "<FeeChange>Y</FeeChange>",
            "<EMSNChange>N</EMSNChange>",
            "<EMSNCap>P</EMSNCap>",
            "<BenefitType>E</BenefitType>",
            "<BenefitStartDate>01.11.2004</BenefitStartDate>",
            "<FeeStartDate>01.07.2026</FeeStartDate>",
            "<ScheduleFee>45.05</ScheduleFee>",
            "<Benefit100>45.05</Benefit100>",
            "<BasicUnits></BasicUnits>",
            "<EMSNStartDate>01.11.2012</EMSNStartDate>",
            "<EMSNEndDate></EMSNEndDate>",
            "<EMSNFixedCapAmount></EMSNFixedCapAmount>",
            "<EMSNMaximumCap>500.00</EMSNMaximumCap>",
            "<EMSNPercentageCap>300.00</EMSNPercentageCap>",
            "<EMSNDescription></EMSNDescription>",
            "<EMSNChangeDate></EMSNChangeDate>",
            "<DescriptionStartDate>01.11.2023</DescriptionStartDate>",
            "<Description>Professional attendance by a general practitioner</Description>",
            "<QFEStartDate></QFEStartDate>",
            "<QFEEndDate></QFEEndDate>",
            "</Data>",
            "<Data>",
            "<ItemNum>24</ItemNum>",
            "<SubItemNum></SubItemNum>",
            "<ItemStartDate>01.12.1989</ItemStartDate>",
            "<ItemEndDate></ItemEndDate>",
            "<Category>1</Category>",
            "<Group>A1</Group>",
            "<SubGroup>1</SubGroup>",
            "<SubHeading>2</SubHeading>",
            "<ItemType>S</ItemType>",
            "<FeeType>D</FeeType>",
            "<ProviderType></ProviderType>",
            "<NewItem>N</NewItem>",
            "<BenefitType>D</BenefitType>",
            "<BenefitStartDate>01.11.2012</BenefitStartDate>",
            "<DerivedFeeStartDate>01.07.2026</DerivedFeeStartDate>",
            "<DerivedFee>The fee for item 23, plus a derived amount.</DerivedFee>",
            "<DescriptionStartDate>01.11.2023</DescriptionStartDate>",
            "<Description>Derived attendance item</Description>",
            "</Data>",
            "</MBS_XML>",
        ],
    )
    return data_root


def _write(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_phi_workbook(path: Path) -> None:
    with ZipFile(path, "w") as zf:
        zf.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="PHI Classifications" sheetId="1" r:id="rId1"/>
    <sheet name="PHI Definitions" sheetId="2" r:id="rId2"/>
    <sheet name="Deleted items list" sheetId="3" r:id="rId3"/>
  </sheets>
</workbook>
""",
        )
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Target="worksheets/sheet1.xml"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/>
  <Relationship Id="rId2" Target="worksheets/sheet2.xml"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/>
  <Relationship Id="rId3" Target="worksheets/sheet3.xml"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/>
</Relationships>
""",
        )
        zf.writestr(
            "xl/worksheets/sheet1.xml",
            _sheet_xml(
                [
                    ["MBS Item", "Clinical Category", "Procedure Type ", "New Item"],
                    ["23", "Common list", "Type C", "N"],
                    ["61470", "Hospital psychiatric services", "Type A", "Y"],
                ]
            ),
        )
        zf.writestr(
            "xl/worksheets/sheet2.xml",
            _sheet_xml(
                [
                    [
                        "Clinical Category:",
                        "Scope of cover: ",
                        "Treatment that must be covered:",
                    ],
                    ["Common list", "Common hospital treatment.", "(No items listed)"],
                    [
                        "Hospital psychiatric services",
                        "Treatment for psychiatric disorders.",
                        "Treatment involving the provision of the following MBS items: 170, 171",
                    ],
                ]
            ),
        )
        zf.writestr(
            "xl/worksheets/sheet3.xml",
            _sheet_xml(
                [
                    ["MBS Item", "Date of Deletion"],
                    ["61470", "46204"],
                ]
            ),
        )


def _sheet_xml(rows: list[list[str]]) -> str:
    row_xml = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for col_index, value in enumerate(row, start=1):
            ref = f"{_column_name(col_index)}{row_index}"
            cells.append(
                f'<c r="{ref}" t="inlineStr"><is><t>{_escape_xml(value)}</t></is></c>'
            )
        row_xml.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(row_xml)}</sheetData>'
        "</worksheet>"
    )


def _column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _escape_xml(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()

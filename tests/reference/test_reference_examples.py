from pathlib import Path

import pytest

from src.domain.rule_parser.rule_set_parser import RuleSetParser
from src.domain.rule_parser.rule_set_reader import RuleSetReader
from src.domain.rule_parser.rule_set_scanner import RuleSetScanner
from src.services.rule_validation_service import RuleValidationService


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_DIR = ROOT / "docs" / "reference" / "examples"


def _reference_example_paths() -> list[Path]:
    return sorted(
        path
        for path in EXAMPLE_DIR.iterdir()
        if path.is_file()
        and path.suffix.lower() == ".txt"
        and path.name.lower().startswith(("vea", "mrca"))
    )


def _validation_error_summary(report) -> list[dict]:
    return [
        {
            "code": error.code,
            "line": error.line,
            "node_name": error.node_name,
            "message": error.message,
        }
        for error in report.errors
    ]


@pytest.mark.parametrize("example_path", _reference_example_paths(), ids=lambda path: path.name)
def test_vea_mrca_reference_examples_validate_and_parse(example_path: Path) -> None:
    rule_text = example_path.read_text(encoding="utf-8")
    assert rule_text.strip(), f"{example_path.name} is empty"

    report = RuleValidationService(cache_ttl_seconds=0).validate(rule_text, example_path.name)
    assert report.valid, _validation_error_summary(report)

    reader = RuleSetReader()
    parser = RuleSetParser()
    parser.create()
    parser.set_source_name(example_path.stem)
    reader.set_file_with_text(rule_text)

    scanner = RuleSetScanner(reader, parser)
    scanner.scan_rule_set()
    node_set = scanner.establish_node_set()
    graph = node_set.get_graph()

    assert node_set.get_input_dictionary()
    assert node_set.get_fact_dictionary()
    assert node_set.get_node_dictionary()
    assert graph is not None
    assert tuple(graph.all_node_names())

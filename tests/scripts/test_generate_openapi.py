from pathlib import Path

from scripts import generate_openapi


SAMPLE_SCHEMA = {
    "openapi": "3.1.0",
    "info": {"version": "2.0.0", "title": "INFERRA Platform API"},
    "paths": {"/z": {}, "/a": {}},
}


def test_serialize_openapi_is_sorted_and_newline_terminated():
    content = generate_openapi.serialize_openapi(SAMPLE_SCHEMA)

    assert content.endswith("\n")
    assert content.index('"info"') < content.index('"openapi"') < content.index('"paths"')
    assert content.index('"/a"') < content.index('"/z"')


def test_canonical_environment_ignores_workstation_inferra_settings(monkeypatch):
    monkeypatch.setenv("INFERRA_AUTH_ENABLED", "true")
    monkeypatch.setenv("INFERRA_LLM_PROVIDER", "workstation-provider")
    monkeypatch.setenv("UNRELATED_SETTING", "preserved")

    generate_openapi._prepare_canonical_environment()

    assert generate_openapi.os.environ["INFERRA_AUTH_ENABLED"] == "false"
    assert "INFERRA_LLM_PROVIDER" not in generate_openapi.os.environ
    assert generate_openapi.os.environ["INFERRA_LOAD_DOTENV"] == "false"
    assert generate_openapi.os.environ["UNRELATED_SETTING"] == "preserved"


def test_write_and_check_openapi_detect_drift(monkeypatch, tmp_path: Path):
    output = tmp_path / "openapi.json"
    monkeypatch.setattr(generate_openapi, "build_openapi_document", lambda: SAMPLE_SCHEMA)

    assert generate_openapi.write_openapi(output) == 0
    assert generate_openapi.check_openapi(output) == 0

    output.write_text("{}\n", encoding="utf-8")

    assert generate_openapi.check_openapi(output) == 1

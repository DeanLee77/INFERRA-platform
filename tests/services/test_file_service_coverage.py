"""Focused safety-limit coverage for document conversion."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from src.services import file_service
from src.services.file_service import (
    FileConversionLimitError,
    _float_setting,
    _int_setting,
    _output_char_limit,
    _raise_if_timed_out,
    _read_text_with_limit,
    handle_docx_file,
    handle_pdf_file,
)


def test_numeric_settings_reject_booleans_and_malformed_values() -> None:
    with patch.object(file_service, "settings") as settings:
        settings.INT_BOOL = True
        settings.INT_BAD = "not-an-integer"
        settings.FLOAT_BOOL = False
        settings.FLOAT_BAD = "not-a-float"

        assert _int_setting("INT_BOOL", 7) == 7
        assert _int_setting("INT_BAD", 8) == 8
        assert _float_setting("FLOAT_BOOL", 1.5) == 1.5
        assert _float_setting("FLOAT_BAD", 2.5) == 2.5


def test_zero_byte_input_uses_configured_output_limit() -> None:
    with patch.object(file_service, "_int_setting", return_value=100), patch.object(
        file_service,
        "_float_setting",
        return_value=10.0,
    ), patch.object(file_service.os.path, "getsize", return_value=0):
        assert _output_char_limit("empty.pdf") == 100


def test_timeout_and_text_output_limits_fail_closed(tmp_path) -> None:
    with patch.object(
        file_service,
        "_conversion_timeout_seconds",
        return_value=1.0,
    ), patch.object(file_service.time, "monotonic", return_value=2.0):
        with pytest.raises(FileConversionLimitError, match="exceeded 1.0 seconds"):
            _raise_if_timed_out(0.0, "PDF")

    text_file = tmp_path / "expanded.md"
    text_file.write_text("12345", encoding="utf-8")
    with pytest.raises(FileConversionLimitError, match="exceeds 4 characters"):
        _read_text_with_limit(str(text_file), 4, "Pandoc")


def test_pdf_iteration_limit_applies_when_document_length_is_unavailable() -> None:
    first_page = MagicMock()
    first_page.get_text.return_value = "first page"
    second_page = MagicMock()
    document = MagicMock()
    document.page_count = None
    document.__len__.side_effect = TypeError("length unavailable")
    document.__iter__.return_value = iter((first_page, second_page))
    fitz = MagicMock()
    fitz.open.return_value = document

    with patch.object(file_service, "_get_fitz", return_value=fitz), patch.object(
        file_service,
        "_int_setting",
        return_value=1,
    ), patch.object(file_service, "_output_char_limit", return_value=1000), patch.object(
        file_service,
        "_raise_if_timed_out",
    ):
        with pytest.raises(FileConversionLimitError, match="page count exceeds limit 1"):
            handle_pdf_file("unbounded.pdf")

    document.close.assert_called_once_with()


def test_docx_conversion_translates_pandoc_process_errors() -> None:
    temporary_output = MagicMock()
    temporary_output.name = "converted-output.md"
    temporary_output.__enter__.return_value = temporary_output
    temporary_output.__exit__.return_value = False
    process_error = subprocess.CalledProcessError(
        returncode=2,
        cmd=["pandoc"],
        stderr="invalid document",
    )

    with patch.object(file_service.shutil, "which", return_value="pandoc"), patch.object(
        file_service.tempfile,
        "NamedTemporaryFile",
        return_value=temporary_output,
    ), patch.object(file_service.subprocess, "run", side_effect=process_error), patch.object(
        file_service.os.path,
        "exists",
        return_value=True,
    ), patch.object(file_service.os, "unlink"):
        with pytest.raises(RuntimeError, match="Pandoc conversion failed: invalid document"):
            handle_docx_file("broken.docx")

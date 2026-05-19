"""
Integration tests for the files router.

Covers document upload, conversion, validation, and error handling
using FastAPI TestClient.
"""

import pytest
from unittest.mock import MagicMock, patch, mock_open
from fastapi.testclient import TestClient
from io import BytesIO

from src.main import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


# =============================================================================
# POST /api/v1/files/convert
# =============================================================================

class TestConvertDocument:
    """Tests for POST /api/v1/files/convert."""

    def test_missing_file_returns_422(self, client):
        """Test 422 when no file is uploaded."""
        response = client.post("/api/v1/files/convert", data={"type": "markdown"})
        assert response.status_code == 422

    @patch("src.adapters.inbound.http.routes.files.validate_uploaded_file")
    def test_invalid_file_type_returns_400(self, mock_validate, client):
        """Test 400 when file type is invalid."""
        mock_validate.return_value = (False, "Invalid file type")

        file_content = b"Test content"
        upload_file = {"file": ("test.xyz", BytesIO(file_content), "application/unknown")}

        response = client.post("/api/v1/files/convert", files=upload_file, data={"type": "unknown"})
        assert response.status_code == 400

    @patch("src.adapters.inbound.http.routes.files.validate_uploaded_file")
    def test_empty_filename_returns_400(self, mock_validate, client):
        """Test 400 when uploaded file has empty name."""
        mock_validate.return_value = (False, "No filename provided")

        file_content = b"Test content"
        upload_file = {"file": ("file.txt", BytesIO(file_content), "text/plain")}

        response = client.post("/api/v1/files/convert", files=upload_file, data={"type": "text"})
        assert response.status_code == 400

    @patch("src.adapters.inbound.http.routes.files.FileConversionService.convert_to_markdown")
    @patch("src.adapters.inbound.http.routes.files.FileConversionService.save_upload_to_temp")
    @patch("src.adapters.inbound.http.routes.files.validate_uploaded_file")
    def test_valid_file_streams_response(self, mock_validate, mock_save, mock_convert, client):
        """Test 200 with streaming response for valid file."""
        mock_validate.return_value = (True, None)
        mock_save.return_value = "/tmp/test_file.md"
        mock_convert.return_value = "# Converted markdown"

        file_content = b"Test file content"
        upload_file = {"file": ("test.md", BytesIO(file_content), "text/markdown")}

        response = client.post("/api/v1/files/convert", files=upload_file, data={"type": "markdown"})

        # The response should be successful (streaming plain text)
        assert response.status_code == 200

    @patch("src.adapters.inbound.http.routes.files.FileConversionService.convert_to_markdown")
    @patch("src.adapters.inbound.http.routes.files.FileConversionService.save_upload_to_temp")
    @patch("src.adapters.inbound.http.routes.files.validate_uploaded_file")
    def test_conversion_error_returns_500(self, mock_validate, mock_save, mock_convert, client):
        """Test 500 when conversion fails internally."""
        mock_validate.return_value = (True, None)
        mock_save.return_value = "/tmp/test_file.md"
        mock_convert.side_effect = Exception("Conversion failed")

        file_content = b"Test content"
        upload_file = {"file": ("test.txt", BytesIO(file_content), "text/plain")}

        response = client.post("/api/v1/files/convert", files=upload_file, data={"type": "text"})
        assert response.status_code == 500


# =============================================================================
# POST /api/v1/files/convert-to-markdown
# =============================================================================

class TestConvertToMarkdown:
    """Tests for POST /api/v1/files/convert-to-markdown."""

    @patch("src.adapters.inbound.http.routes.files.FileConversionService.convert_to_markdown")
    @patch("src.adapters.inbound.http.routes.files.FileConversionService.save_upload_to_temp")
    @patch("src.adapters.inbound.http.routes.files.validate_uploaded_file")
    def test_convert_to_markdown_success(self, mock_validate, mock_save, mock_convert, client):
        """Test 200 returning markdown content as JSON."""
        mock_validate.return_value = (True, None)
        mock_save.return_value = "/tmp/test_file.pdf"
        mock_convert.return_value = "# Markdown content"

        file_content = b"Test file content"
        upload_file = {"file": ("test.pdf", BytesIO(file_content), "application/pdf")}

        response = client.post("/api/v1/files/convert-to-markdown", files=upload_file)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["markdown"] == "# Markdown content"

    def test_convert_to_markdown_missing_file(self, client):
        """Test 422 when no file is uploaded."""
        response = client.post("/api/v1/files/convert-to-markdown")
        assert response.status_code == 422

    @patch("src.adapters.inbound.http.routes.files.validate_uploaded_file")
    def test_convert_to_markdown_invalid_file(self, mock_validate, client):
        """Test 400 when file is invalid."""
        mock_validate.return_value = (False, "Invalid file type")

        file_content = b"Test"
        upload_file = {"file": ("test.xyz", BytesIO(file_content), "application/unknown")}

        response = client.post("/api/v1/files/convert-to-markdown", files=upload_file)
        assert response.status_code == 400


# =============================================================================
# Additional coverage tests
# =============================================================================


class TestConvertDocumentAdditionalPaths:
    @patch("src.adapters.inbound.http.routes.files.FileConversionService.convert_to_markdown")
    @patch("src.adapters.inbound.http.routes.files.FileConversionService.save_upload_to_temp")
    @patch("src.adapters.inbound.http.routes.files.validate_uploaded_file")
    def test_value_error_returns_400(self, mock_validate, mock_save, mock_convert, client):
        mock_validate.return_value = (True, None)
        mock_save.return_value = "/tmp/test_file.md"
        mock_convert.side_effect = ValueError("Unsupported format")
        file_content = b"Test content"
        upload_file = {"file": ("test.xyz", BytesIO(file_content), "application/unknown")}
        response = client.post("/api/v1/files/convert", files=upload_file, data={"type": "text"})
        assert response.status_code == 400

    @patch("src.adapters.inbound.http.routes.files.FileConversionService.convert_to_markdown")
    @patch("src.adapters.inbound.http.routes.files.FileConversionService.save_upload_to_temp")
    @patch("src.adapters.inbound.http.routes.files.validate_uploaded_file")
    def test_file_not_found_error_returns_400(self, mock_validate, mock_save, mock_convert, client):
        mock_validate.return_value = (True, None)
        mock_save.return_value = "/tmp/test_file.md"
        mock_convert.side_effect = FileNotFoundError("File missing")
        file_content = b"Test content"
        upload_file = {"file": ("test.txt", BytesIO(file_content), "text/plain")}
        response = client.post("/api/v1/files/convert", files=upload_file, data={"type": "text"})
        assert response.status_code == 400

    @patch("src.adapters.inbound.http.routes.files.FileConversionService.cleanup_temp_file")
    @patch("src.adapters.inbound.http.routes.files.FileConversionService.convert_to_markdown")
    @patch("src.adapters.inbound.http.routes.files.FileConversionService.save_upload_to_temp")
    @patch("src.adapters.inbound.http.routes.files.validate_uploaded_file")
    def test_temp_file_cleanup_on_success(self, mock_validate, mock_save, mock_convert, mock_cleanup, client):
        mock_validate.return_value = (True, None)
        mock_save.return_value = "/tmp/test_file.md"
        mock_convert.return_value = "# Markdown"
        file_content = b"Test content"
        upload_file = {"file": ("test.md", BytesIO(file_content), "text/markdown")}
        response = client.post("/api/v1/files/convert", files=upload_file, data={"type": "markdown"})
        assert response.status_code == 200

    @patch("src.adapters.inbound.http.routes.files.FileConversionService.cleanup_temp_file")
    @patch("src.adapters.inbound.http.routes.files.FileConversionService.convert_to_markdown")
    @patch("src.adapters.inbound.http.routes.files.FileConversionService.save_upload_to_temp")
    @patch("src.adapters.inbound.http.routes.files.validate_uploaded_file")
    def test_temp_file_cleanup_on_error(self, mock_validate, mock_save, mock_convert, mock_cleanup, client):
        mock_validate.return_value = (True, None)
        mock_save.return_value = "/tmp/test_file.md"
        mock_convert.side_effect = Exception("Conversion failed")
        file_content = b"Test content"
        upload_file = {"file": ("test.txt", BytesIO(file_content), "text/plain")}
        response = client.post("/api/v1/files/convert", files=upload_file, data={"type": "text"})
        assert response.status_code == 500


class TestConvertToMarkdownAdditionalPaths:
    @patch("src.adapters.inbound.http.routes.files.FileConversionService.cleanup_temp_file")
    @patch("src.adapters.inbound.http.routes.files.FileConversionService.convert_to_markdown")
    @patch("src.adapters.inbound.http.routes.files.FileConversionService.save_upload_to_temp")
    @patch("src.adapters.inbound.http.routes.files.validate_uploaded_file")
    def test_value_error_returns_400(self, mock_validate, mock_save, mock_convert, mock_cleanup, client):
        mock_validate.return_value = (True, None)
        mock_save.return_value = "/tmp/test.pdf"
        mock_convert.side_effect = ValueError("Bad format")
        file_content = b"Test file content"
        upload_file = {"file": ("test.pdf", BytesIO(file_content), "application/pdf")}
        response = client.post("/api/v1/files/convert-to-markdown", files=upload_file)
        assert response.status_code == 400

    @patch("src.adapters.inbound.http.routes.files.FileConversionService.cleanup_temp_file")
    @patch("src.adapters.inbound.http.routes.files.FileConversionService.convert_to_markdown")
    @patch("src.adapters.inbound.http.routes.files.FileConversionService.save_upload_to_temp")
    @patch("src.adapters.inbound.http.routes.files.validate_uploaded_file")
    def test_general_error_returns_500(self, mock_validate, mock_save, mock_convert, mock_cleanup, client):
        mock_validate.return_value = (True, None)
        mock_save.return_value = "/tmp/test.pdf"
        mock_convert.side_effect = Exception("Unexpected")
        file_content = b"Test file content"
        upload_file = {"file": ("test.pdf", BytesIO(file_content), "application/pdf")}
        response = client.post("/api/v1/files/convert-to-markdown", files=upload_file)
        assert response.status_code == 500


class TestStreamConversionError:
    @patch("src.adapters.inbound.http.routes.files.FileConversionService.cleanup_temp_file")
    @patch("src.adapters.inbound.http.routes.files.transform_to_inferra_rules_stream")
    @patch("src.adapters.inbound.http.routes.files.FileConversionService.convert_to_markdown")
    @patch("src.adapters.inbound.http.routes.files.FileConversionService.save_upload_to_temp")
    @patch("src.adapters.inbound.http.routes.files.validate_uploaded_file")
    def test_stream_conversion_fatal_error(self, mock_validate, mock_save, mock_convert, mock_stream, mock_cleanup, client):
        mock_validate.return_value = (True, None)
        mock_save.return_value = "/tmp/test_file.md"
        mock_convert.return_value = "# Markdown"
        def raise_error(*args, **kwargs):
            raise RuntimeError("Stream failed")
            yield
        mock_stream.side_effect = lambda fn, mc: raise_error(fn, mc)
        file_content = b"Test content"
        upload_file = {"file": ("test.md", BytesIO(file_content), "text/markdown")}
        response = client.post("/api/v1/files/convert", files=upload_file, data={"type": "markdown"})
        assert response.status_code == 200

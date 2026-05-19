"""
Tests for the FileConversionService.
"""

import pytest
from unittest.mock import MagicMock, patch, mock_open
import os

from src.services.file_service import (
    FileConversionService,
    validate_uploaded_file,
    preprocess_text,
    handle_pdf_file,
    handle_docx_file,
    convert_file_to_markdown,
)


@pytest.fixture
def file_service():
    """Create a FileConversionService instance."""
    return FileConversionService()


class TestValidateUploadedFile:
    """Tests for validate_uploaded_file function."""
    
    def test_validate_uploaded_file_no_filename(self):
        """Test file validation when no filename is provided."""
        is_valid, error_msg = validate_uploaded_file("", "application/pdf", 100)
        
        assert is_valid is False
        assert error_msg == "No filename provided"
    
    def test_validate_uploaded_file_path_traversal(self):
        """Test file validation with path traversal attempt."""
        is_valid, error_msg = validate_uploaded_file("../etc/passwd", "application/pdf", 100)
        
        assert is_valid is False
        assert error_msg == "Invalid filename"
    
    def test_validate_uploaded_file_empty_file(self):
        """Test file validation with empty file."""
        with patch("src.services.file_service.settings") as mock_settings:
            mock_settings.ALLOWED_EXTENSIONS = [".pdf"]
            mock_settings.ALLOWED_MIMES = ["application/pdf"]
            mock_settings.MAX_CONTENT_LENGTH = 10000000
            
            is_valid, error_msg = validate_uploaded_file("test.pdf", "application/pdf", 0)
            
            assert is_valid is False
            assert error_msg == "Empty file"


class TestFileConversionService:
    """Tests for FileConversionService."""
    
    def test_convert_to_markdown_md_file(self, file_service):
        """Test converting markdown file."""
        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data="# Markdown content")), \
             patch("src.services.file_service.preprocess_text", side_effect=lambda x: x):
            
            result = file_service.convert_to_markdown("/tmp/test.md")
            
            assert result == "# Markdown content"
    
    def test_convert_to_markdown_file_not_found(self, file_service):
        """Test error when file not found."""
        with patch("os.path.exists", return_value=False):
            with pytest.raises(FileNotFoundError):
                file_service.convert_to_markdown("/tmp/nonexistent.md")
    
    def test_convert_to_markdown_unsupported_format(self, file_service):
        """Test error for unsupported file format."""
        with patch("os.path.exists", return_value=True):
            with pytest.raises(ValueError, match="Unsupported file format"):
                file_service.convert_to_markdown("/tmp/test.xyz")
    
    def test_cleanup_temp_file_exists(self, file_service):
        """Test cleaning up existing temporary file."""
        with patch("os.path.exists", return_value=True), \
             patch("os.unlink") as mock_unlink:
            
            file_service.cleanup_temp_file("/tmp/test_file.md")
            
            mock_unlink.assert_called_once_with("/tmp/test_file.md")
    
    def test_cleanup_temp_file_not_exists(self, file_service):
        """Test cleaning up non-existent temporary file."""
        with patch("os.path.exists", return_value=False), \
             patch("os.unlink") as mock_unlink:
            
            file_service.cleanup_temp_file("/tmp/test_file.md")
            
            mock_unlink.assert_not_called()
    
    def test_cleanup_temp_file_error(self, file_service):
        """Test cleanup handles errors gracefully."""
        with patch("os.path.exists", return_value=True), \
             patch("os.unlink", side_effect=PermissionError("Access denied")):
            
            file_service.cleanup_temp_file("/tmp/test_file.md")
    
    @pytest.mark.asyncio
    async def test_save_upload_to_temp(self, file_service):
        """Test saving uploaded file to temporary location."""
        content = b"file content"
        
        with patch("tempfile.NamedTemporaryFile") as mock_temp:
            mock_file = MagicMock()
            mock_file.write = MagicMock()
            mock_file.name = "/tmp/test_file.md"
            mock_file.__enter__ = MagicMock(return_value=mock_file)
            mock_file.__exit__ = MagicMock(return_value=False)
            mock_temp.return_value = mock_file
            
            result = await file_service.save_upload_to_temp(content, ".md")
            
            mock_temp.assert_called_once_with(delete=False, suffix=".md")
            mock_file.write.assert_called_once_with(content)


class TestPreprocessText:
    """Tests for preprocess_text function."""

    def test_preprocess_text_superscript_digits(self):
        result = preprocess_text("⁰¹²³⁴⁵⁶⁷⁸⁹")
        assert "0" in result
        assert "1" in result

    def test_preprocess_text_coordinate_pattern(self):
        result = preprocess_text("12 34 N")
        assert "N" in result

    def test_preprocess_text_returns_string(self):
        result = preprocess_text("some input")
        assert isinstance(result, str)

    def test_preprocess_text_preserves_plain_text(self):
        assert preprocess_text("some input") == "some input"

    def test_preprocess_text_unicode_replacements(self):
        result = preprocess_text("′")
        assert isinstance(result, str)

    def test_preprocess_text_years_pattern(self):
        result = preprocess_text("5 years + extra")
        assert isinstance(result, str)


class TestValidateUploadedFileExtended:
    """Extended tests for validate_uploaded_file function."""

    def test_validate_uploaded_file_valid_pdf(self):
        with patch("src.services.file_service.settings") as mock_settings:
            mock_settings.ALLOWED_EXTENSIONS = [".pdf"]
            mock_settings.ALLOWED_MIMES = ["application/pdf"]
            mock_settings.MAX_CONTENT_LENGTH = 10000000
            is_valid, error_msg = validate_uploaded_file("test.pdf", "application/pdf", 100)
            assert is_valid is True
            assert error_msg == "OK"

    def test_validate_uploaded_file_unsupported_extension(self):
        with patch("src.services.file_service.settings") as mock_settings:
            mock_settings.ALLOWED_EXTENSIONS = [".pdf"]
            mock_settings.ALLOWED_MIMES = ["application/pdf"]
            mock_settings.MAX_CONTENT_LENGTH = 10000000
            is_valid, error_msg = validate_uploaded_file("test.exe", "application/pdf", 100)
            assert is_valid is False
            assert "Unsupported extension" in error_msg

    def test_validate_uploaded_file_unsupported_mime(self):
        with patch("src.services.file_service.settings") as mock_settings:
            mock_settings.ALLOWED_EXTENSIONS = [".pdf"]
            mock_settings.ALLOWED_MIMES = ["application/pdf"]
            mock_settings.MAX_CONTENT_LENGTH = 10000000
            is_valid, error_msg = validate_uploaded_file("test.pdf", "application/exe", 100)
            assert is_valid is False
            assert "Unsupported MIME type" in error_msg

    def test_validate_uploaded_file_too_large(self):
        with patch("src.services.file_service.settings") as mock_settings:
            mock_settings.ALLOWED_EXTENSIONS = [".pdf"]
            mock_settings.ALLOWED_MIMES = ["application/pdf"]
            mock_settings.MAX_CONTENT_LENGTH = 100
            is_valid, error_msg = validate_uploaded_file("test.pdf", "application/pdf", 200)
            assert is_valid is False
            assert "too large" in error_msg

    def test_validate_uploaded_file_empty_mime_accepted(self):
        with patch("src.services.file_service.settings") as mock_settings:
            mock_settings.ALLOWED_EXTENSIONS = [".pdf"]
            mock_settings.ALLOWED_MIMES = ["application/pdf"]
            mock_settings.MAX_CONTENT_LENGTH = 10000000
            is_valid, error_msg = validate_uploaded_file("test.pdf", "", 100)
            assert is_valid is True
            assert error_msg == "OK"

    def test_validate_uploaded_file_none_filename(self):
        is_valid, error_msg = validate_uploaded_file(None, "application/pdf", 100)
        assert is_valid is False


class TestHandlePdfFile:
    """Tests for handle_pdf_file function."""

    def test_handle_pdf_file_fitz_not_installed(self):
        with patch("src.services.file_service._get_fitz", return_value=None):
            with pytest.raises(RuntimeError, match="PyMuPDF"):
                handle_pdf_file("/tmp/test.pdf")

    def test_handle_pdf_file_success(self):
        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_page.get_text.return_value = "Page content"
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
        mock_doc.close = MagicMock()

        mock_fitz = MagicMock()
        mock_fitz.open.return_value = mock_doc

        with patch("src.services.file_service._get_fitz", return_value=mock_fitz):
            result = handle_pdf_file("/tmp/test.pdf")
            assert "Page content" in result
            mock_doc.close.assert_called_once()

    def test_handle_pdf_file_exception_returns_error_string(self):
        mock_fitz = MagicMock()
        mock_fitz.open.side_effect = Exception("Cannot open")

        with patch("src.services.file_service._get_fitz", return_value=mock_fitz):
            result = handle_pdf_file("/tmp/bad.pdf")
            assert "PDF extraction error" in result

    def test_handle_pdf_file_multiple_pages(self):
        mock_doc = MagicMock()
        page1 = MagicMock()
        page1.get_text.return_value = "Page 1"
        page2 = MagicMock()
        page2.get_text.return_value = "Page 2"
        mock_doc.__iter__ = MagicMock(return_value=iter([page1, page2]))
        mock_doc.close = MagicMock()

        mock_fitz = MagicMock()
        mock_fitz.open.return_value = mock_doc

        with patch("src.services.file_service._get_fitz", return_value=mock_fitz):
            result = handle_pdf_file("/tmp/multi.pdf")
            assert "Page 1" in result
            assert "Page 2" in result


class TestHandleDocxFile:
    """Tests for handle_docx_file function."""

    def test_handle_docx_file_success(self):
        with patch("pypandoc.convert_file") as mock_convert, \
             patch("builtins.open", mock_open(read_data="# Converted markdown")), \
             patch("os.path.exists", return_value=True), \
             patch("os.unlink"):
            mock_convert.return_value = None
            result = handle_docx_file("/tmp/test.docx")
            assert result == "# Converted markdown"

    def test_handle_docx_file_doc_format(self):
        with patch("pypandoc.convert_file") as mock_convert, \
             patch("builtins.open", mock_open(read_data="# Doc content")), \
             patch("os.path.exists", return_value=True), \
             patch("os.unlink"):
            mock_convert.return_value = None
            result = handle_docx_file("/tmp/test.doc")
            assert result == "# Doc content"


class TestConvertFileToMarkdown:
    """Tests for convert_file_to_markdown function."""

    def test_convert_file_not_found(self):
        with patch("os.path.exists", return_value=False):
            with pytest.raises(FileNotFoundError, match="File does not exist"):
                convert_file_to_markdown("/tmp/nonexistent.pdf")

    def test_convert_markdown_file(self):
        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data="# Markdown")), \
             patch("src.services.file_service.preprocess_text", side_effect=lambda x: x):
            result = convert_file_to_markdown("/tmp/test.md")
            assert result == "# Markdown"

    def test_convert_markdown_extension(self):
        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data="# Content")), \
             patch("src.services.file_service.preprocess_text", side_effect=lambda x: x):
            result = convert_file_to_markdown("/tmp/test.markdown")
            assert result == "# Content"

    def test_convert_pdf_file(self):
        mock_fitz = MagicMock()
        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_page.get_text.return_value = "PDF content"
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
        mock_doc.close = MagicMock()
        mock_fitz.open.return_value = mock_doc

        with patch("os.path.exists", return_value=True), \
             patch("src.services.file_service._get_fitz", return_value=mock_fitz), \
             patch("src.services.file_service.preprocess_text", side_effect=lambda x: x):
            result = convert_file_to_markdown("/tmp/test.pdf")
            assert "PDF content" in result

    def test_convert_unsupported_format_raises_value_error(self):
        with patch("os.path.exists", return_value=True):
            with pytest.raises(ValueError, match="Unsupported file format"):
                convert_file_to_markdown("/tmp/test.xyz")


class TestFileConversionServiceExtended:
    """Extended tests for FileConversionService."""

    def test_convert_to_markdown_pdf(self, file_service):
        mock_fitz = MagicMock()
        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_page.get_text.return_value = "PDF text"
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
        mock_doc.close = MagicMock()
        mock_fitz.open.return_value = mock_doc

        with patch("os.path.exists", return_value=True), \
             patch("src.services.file_service._get_fitz", return_value=mock_fitz), \
             patch("src.services.file_service.preprocess_text", side_effect=lambda x: x):
            result = file_service.convert_to_markdown("/tmp/test.pdf")
            assert "PDF text" in result

    def test_cleanup_temp_file_empty_path(self, file_service):
        with patch("os.path.exists", return_value=False), \
             patch("os.unlink") as mock_unlink:
            file_service.cleanup_temp_file("")
            mock_unlink.assert_not_called()

    def test_cleanup_temp_file_none_path(self, file_service):
        with patch("os.path.exists", return_value=False), \
             patch("os.unlink") as mock_unlink:
            file_service.cleanup_temp_file(None)
            mock_unlink.assert_not_called()


class TestGetFitzLazyLoad:
    def test_get_fitz_import_error_returns_none(self):
        import src.services.file_service as fs
        original = fs.fitz
        fs.fitz = None
        with patch.dict("sys.modules", {"fitz": None}):
            result = fs._get_fitz()
            assert result is None
        fs.fitz = original

    def test_get_fitz_caches_after_first_load(self):
        import src.services.file_service as fs
        original = fs.fitz
        mock_fitz = MagicMock()
        fs.fitz = None
        with patch.dict("sys.modules", {"fitz": mock_fitz}):
            with patch("importlib.import_module", return_value=mock_fitz):
                result1 = fs._get_fitz()
                result2 = fs._get_fitz()
                assert result1 is result2
        fs.fitz = original


class TestHandleDocxFileOSErrorPath:
    def test_handle_docx_file_oserror_downloads_pandoc(self):
        mock_f = MagicMock()
        mock_f.write = MagicMock()
        mock_f.name = "/tmp/test_out.md"
        mock_f.__enter__ = MagicMock(return_value=mock_f)
        mock_f.__exit__ = MagicMock(return_value=False)

        with patch("pypandoc.convert_file", side_effect=[OSError("pandoc not found"), None]), \
             patch("pypandoc.download_pandoc"), \
             patch("tempfile.NamedTemporaryFile", return_value=mock_f), \
             patch("builtins.open", mock_open(read_data="# Converted")), \
             patch("os.path.exists", return_value=True), \
             patch("os.unlink"):
            result = handle_docx_file("/tmp/test.docx")
            assert result == "# Converted"

    def test_handle_docx_file_oserror_no_ssl_attr(self):
        import ssl
        mock_f = MagicMock()
        mock_f.write = MagicMock()
        mock_f.name = "/tmp/test_out.md"
        mock_f.__enter__ = MagicMock(return_value=mock_f)
        mock_f.__exit__ = MagicMock(return_value=False)

        original_ctx = ssl._create_unverified_context
        del ssl._create_unverified_context
        try:
            with patch("pypandoc.convert_file", side_effect=[OSError("pandoc not found"), None]), \
                 patch("pypandoc.download_pandoc"), \
                 patch("tempfile.NamedTemporaryFile", return_value=mock_f), \
                 patch("builtins.open", mock_open(read_data="# Converted")), \
                 patch("os.path.exists", return_value=True), \
                 patch("os.unlink"):
                result = handle_docx_file("/tmp/test.docx")
                assert result == "# Converted"
        finally:
            ssl._create_unverified_context = original_ctx


class TestConvertFileToMarkdownDoc:
    def test_convert_doc_file(self):
        with patch("os.path.exists", return_value=True), \
             patch("src.services.file_service.handle_docx_file", return_value="Doc content"), \
             patch("src.services.file_service.preprocess_text", side_effect=lambda x: x):
            result = convert_file_to_markdown("/tmp/test.doc")
            assert result == "Doc content"

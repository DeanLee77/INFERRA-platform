"""
File Service Module.
Handles file validation, conversion, and transformation.
"""

import os
import re
import shutil
import subprocess
import tempfile
import time
from typing import Tuple

from src.config import settings
from src.infrastructure.logging_config import get_logger

_logger = get_logger(__name__)

# Lazy imports for optional dependencies
fitz = None


class FileConversionLimitError(ValueError):
    """Raised when a document conversion crosses a configured safety limit."""


def _int_setting(name: str, default: int) -> int:
    value = getattr(settings, name, default)
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float, str)):
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return parsed if parsed > 0 else default
    return default


def _float_setting(name: str, default: float) -> float:
    value = getattr(settings, name, default)
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float, str)):
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return default
        return parsed if parsed > 0 else default
    return default


def _conversion_timeout_seconds() -> float:
    return _float_setting("DOCUMENT_CONVERSION_TIMEOUT_SECONDS", 20.0)


def _output_char_limit(file_path: str) -> int:
    configured_limit = _int_setting("DOCUMENT_CONVERSION_MAX_OUTPUT_CHARS", 200000)
    expansion_ratio = _float_setting("DOCUMENT_CONVERSION_MAX_EXPANSION_RATIO", 100.0)
    try:
        input_size = os.path.getsize(file_path)
    except OSError:
        return configured_limit
    if input_size <= 0:
        return configured_limit
    expansion_limit = max(1, int(input_size * expansion_ratio))
    return min(configured_limit, expansion_limit)


def _raise_if_timed_out(start_time: float, source: str) -> None:
    timeout = _conversion_timeout_seconds()
    elapsed = time.monotonic() - start_time
    if elapsed > timeout:
        raise FileConversionLimitError(
            f"{source} conversion exceeded {timeout:.1f} seconds"
        )


def _read_text_with_limit(file_path: str, max_chars: int, source: str) -> str:
    chunks = []
    total_chars = 0
    with open(file_path, 'r', encoding='utf-8') as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            total_chars += len(chunk)
            if total_chars > max_chars:
                raise FileConversionLimitError(
                    f"{source} conversion output exceeds {max_chars} characters"
                )
            chunks.append(chunk)
    return "".join(chunks)


def _get_fitz():
    """Lazy load PyMuPDF (fitz) only when needed."""
    global fitz
    if fitz is None:
        try:
            import fitz as _fitz
            fitz = _fitz
        except ImportError:
            pass
    return fitz


def preprocess_text(text: str) -> str:
    """
    Preprocess text by normalizing special characters.
    
    Args:
        text: Raw text to preprocess
        
    Returns:
        Preprocessed text
    """
    text = re.sub(r'(\d+)(\d+)([NSEW])', r'\1°\2′\3', text)
    replacements = {
        '´': ')',
        '′': "'",
        '‴': "''",
        '⁰': '0',
        '¹': '1',
        '²': '2',
        '³': '3',
        '⁴': '4',
        '⁵': '5',
        '⁶': '6',
        '⁷': '7',
        '⁸': '8',
        '⁹': '9',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r'(\d+)\s*years?\s*´\s*\+\s*', r'(\1 years) + ', text)
    text = re.sub(r'(\d+)\s*years?\s*\+\s*', r'(\1 years) + ', text)
    return text


def validate_uploaded_file(
    filename: str,
    content_type: str,
    file_size: int,
) -> Tuple[bool, str]:
    """
    Validate an uploaded file.
    
    Args:
        filename: Name of the uploaded file
        content_type: MIME type of the file
        file_size: Size of the file in bytes
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not filename:
        return False, "No filename provided"
    
    # Allowed extensions and MIME types are now native List[str] from Pydantic settings
    allowed_extensions = settings.ALLOWED_EXTENSIONS
    allowed_mimes = settings.ALLOWED_MIMES
    
    # Sanitize filename (basic sanitization - remove path separators)
    safe_filename = os.path.basename(filename)
    if safe_filename != filename:
        return False, "Invalid filename"
    
    # Check extension
    ext = os.path.splitext(filename)[1].lower()
    if ext not in allowed_extensions:
        return False, f"Unsupported extension: {ext}"
    
    # Check MIME type
    if content_type and content_type not in allowed_mimes:
        return False, f"Unsupported MIME type: {content_type}"
    
    # Check file size
    if file_size == 0:
        return False, "Empty file"
    
    if file_size > settings.MAX_CONTENT_LENGTH:
        return False, f"File too large (max {settings.MAX_CONTENT_LENGTH} bytes)"
    
    return True, "OK"


def handle_pdf_file(file_path: str) -> str:
    """
    Extract text from a PDF file.
    
    Args:
        file_path: Path to the PDF file
        
    Returns:
        Extracted text content
        
    Raises:
        RuntimeError: If PyMuPDF is not installed
    """
    fitz = _get_fitz()
    if fitz is None:
        raise RuntimeError("PyMuPDF (fitz) is required for PDF conversion but is not installed")
    
    doc = None
    try:
        start_time = time.monotonic()
        max_pages = _int_setting("DOCUMENT_CONVERSION_MAX_PDF_PAGES", 100)
        max_chars = _output_char_limit(file_path)
        doc = fitz.open(file_path)
        page_count = getattr(doc, "page_count", None)
        if not isinstance(page_count, int):
            try:
                page_count = len(doc)
            except TypeError:
                page_count = None
        if page_count is not None and page_count > max_pages:
            raise FileConversionLimitError(
                f"PDF page count {page_count} exceeds limit {max_pages}"
            )

        parts = []
        total_chars = 0
        for page_index, page in enumerate(doc, start=1):
            if page_index > max_pages:
                raise FileConversionLimitError(
                    f"PDF page count exceeds limit {max_pages}"
                )
            _raise_if_timed_out(start_time, "PDF")
            page_text = page.get_text()
            total_chars += len(page_text) + 1
            if total_chars > max_chars:
                raise FileConversionLimitError(
                    f"PDF conversion output exceeds {max_chars} characters"
                )
            parts.append(page_text)
        _raise_if_timed_out(start_time, "PDF")
        return "\n".join(parts) + ("\n" if parts else "")
    except FileConversionLimitError:
        raise
    except Exception as exc:
        _logger.exception("pdf_extraction_failed", file_path=file_path, error=str(exc))
        return '[PDF extraction error: Unable to open PDF file.]'
    finally:
        if doc is not None:
            doc.close()


def handle_docx_file(file_path: str) -> str:
    """
    Convert a DOCX/DOC file to markdown using the installed pandoc executable.
    
    Args:
        file_path: Path to the DOCX/DOC file
        
    Returns:
        Markdown content
        
    Raises:
        RuntimeError: If conversion fails
    """
    ext = os.path.splitext(file_path)[1].lower()
    pandoc_format = ext.lstrip('.')
    pandoc_path = shutil.which("pandoc")
    if pandoc_path is None:
        raise RuntimeError("Pandoc executable is not installed; DOC/DOCX conversion is unavailable")
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.md') as temp_md:
        temp_md_path = temp_md.name
    
    try:
        start_time = time.monotonic()
        try:
            subprocess.run(
                [
                    pandoc_path,
                    file_path,
                    f"--from={pandoc_format}",
                    "--to=markdown",
                    "--wrap=none",
                    "--sandbox",
                    f"--output={temp_md_path}",
                ],
                check=True,
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                timeout=_conversion_timeout_seconds(),
            )
        except subprocess.TimeoutExpired as exc:
            raise FileConversionLimitError(
                f"Pandoc conversion exceeded {_conversion_timeout_seconds():.1f} seconds"
            ) from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or exc.stdout or "").strip()
            detail = f": {stderr}" if stderr else ""
            raise RuntimeError(f"Pandoc conversion failed{detail}") from exc
        _raise_if_timed_out(start_time, "Pandoc")
        return _read_text_with_limit(
            temp_md_path,
            _output_char_limit(file_path),
            "Pandoc",
        )
    finally:
        if temp_md_path and os.path.exists(temp_md_path):
            os.unlink(temp_md_path)


def convert_file_to_markdown(file_path: str) -> str:
    """
    Convert a file to markdown format.
    
    Supports PDF and DOCX/DOC files.
    
    Args:
        file_path: Path to the file to convert
        
    Returns:
        Markdown content
        
    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file format is not supported
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File does not exist: {file_path}")
    
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == '.pdf':
        markdown_content = handle_pdf_file(file_path)
    elif ext in ('.docx', '.doc'):
        markdown_content = handle_docx_file(file_path)
    elif ext in ('.md', '.markdown'):
        # Already markdown, just read it
        with open(file_path, 'r', encoding='utf-8') as f:
            markdown_content = f.read()
    else:
        raise ValueError(f"Unsupported file format: {ext}")
    
    return preprocess_text(markdown_content)


class FileConversionService:
    """Service for file conversion and transformation."""
    
    @staticmethod
    async def save_upload_to_temp(file_content: bytes, suffix: str) -> str:
        """
        Save uploaded file content to a temporary file.
        
        Args:
            file_content: Raw file content
            suffix: File extension (including dot)
            
        Returns:
            Path to the temporary file
        """
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            tmp_file.write(file_content)
            return tmp_file.name
    
    @staticmethod
    def convert_to_markdown(file_path: str) -> str:
        """
        Convert a file to markdown.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Markdown content
        """
        return convert_file_to_markdown(file_path)
    
    @staticmethod
    def cleanup_temp_file(file_path: str) -> None:
        """
        Clean up a temporary file.
        
        Args:
            file_path: Path to the file to delete
        """
        try:
            if file_path and os.path.exists(file_path):
                os.unlink(file_path)
                _logger.debug(f"Cleaned up temp file: {file_path}")
        except Exception as e:
            _logger.warning(f"Failed to cleanup temp file {file_path}: {e}")

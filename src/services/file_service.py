"""
File Service Module.
Handles file validation, conversion, and transformation.
"""

import os
import re
import tempfile
from typing import Tuple, AsyncGenerator

from src.config import settings
from src.shared.loggers import Logger

_logger: Logger = Logger.get_logger(__name__)

# Lazy imports for optional dependencies
fitz = None


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
        doc = fitz.open(file_path)
        markdown_content = ""
        for page in doc:
            markdown_content += page.get_text() + "\n"
        return markdown_content
    except Exception as exc:
        _logger.exception("Failed to extract PDF content from '%s': %s", file_path, exc)
        return '[PDF extraction error: Unable to open PDF file.]'
    finally:
        if doc is not None:
            doc.close()


def handle_docx_file(file_path: str) -> str:
    """
    Convert a DOCX/DOC file to markdown using pypandoc.
    
    Args:
        file_path: Path to the DOCX/DOC file
        
    Returns:
        Markdown content
        
    Raises:
        RuntimeError: If conversion fails
    """
    import pypandoc
    import ssl
    
    ext = os.path.splitext(file_path)[1].lower()
    pandoc_format = ext.lstrip('.')
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.md') as temp_md:
        temp_md_path = temp_md.name
    
    try:
        try:
            pypandoc.convert_file(
                file_path,
                'markdown',
                outputfile=temp_md_path,
                format=pandoc_format,
                extra_args=['--wrap=none']
            )
        except OSError:
            # Try downloading pandoc if not available
            try:
                _create_unverified_https_context = ssl._create_unverified_context
            except AttributeError:
                pass
            else:
                ssl._create_default_https_context = _create_unverified_https_context
            pypandoc.download_pandoc()
            pypandoc.convert_file(
                file_path,
                'markdown',
                outputfile=temp_md_path,
                format=pandoc_format,
                extra_args=['--wrap=none']
            )
        
        with open(temp_md_path, 'r', encoding='utf-8') as f:
            markdown_content = f.read()
        
        return markdown_content
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

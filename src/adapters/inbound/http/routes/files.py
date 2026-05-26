"""
Files API Router.
Handles document conversion and streaming transformation.
"""

import os
from typing import AsyncGenerator

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from src.adapters.outbound.llm.streamer import transform_to_inferra_rules_stream
from src.adapters.inbound.http.schemas.files import ConversionError
from src.infrastructure.logging_config import get_logger
from src.services.file_service import FileConversionService, validate_uploaded_file

router = APIRouter(prefix="/api/v1/files", tags=["files"])
logger = get_logger("inferra.fastapi.files")


async def _stream_conversion(
    file_name: str,
    markdown_content: str,
    llm_provider: str = "",
    llm_model: str = "",
) -> AsyncGenerator[str, None]:
    """
    Async generator that wraps the sync streamer.
    
    Args:
        file_name: Name of the original file
        markdown_content: Converted markdown content
        
    Yields:
        Chunks of transformed content
    """
    try:
        kwargs = {}
        if llm_provider:
            kwargs["provider_id"] = llm_provider
        if llm_model:
            kwargs["model_id"] = llm_model
        for chunk in transform_to_inferra_rules_stream(file_name, markdown_content, **kwargs):
            yield chunk
    except Exception as exc:
        logger.exception("streaming_conversion_failed", error=str(exc))
        yield f"[FATAL_ERROR] {str(exc)}\n"


@router.post(
    "/convert",
    responses={
        200: {
            "description": "Streaming response with converted INFERRA rules",
            "content": {"text/plain": {}},
        },
        400: {"model": ConversionError},
        413: {"model": ConversionError},
        500: {"model": ConversionError},
    },
)
async def convert_document(
    file: UploadFile = File(..., description="Document file to convert"),
    file_type: str = Form(default="", description="File type hint"),
    llm_provider: str = Form(default="", description="Optional LLM provider id"),
    llm_model: str = Form(default="", description="Optional LLM model id"),
) -> StreamingResponse:
    """
    Convert a document to INFERRA rules format.
    
    This endpoint:
    1. Validates the uploaded file
    2. Converts it to markdown (PDF, DOCX, DOC, MD supported)
    3. Streams the LLM-transformed INFERRA rules output
    
    The response is streamed as plain text chunks. The stream ends with
    `__STREAM_COMPLETE__` marker on success, or an error message on failure.
    
    Supported file types: .pdf, .docx, .doc, .md, .markdown
    """
    logger.info(
        "file_upload_received",
        filename=file.filename,
        content_type=file.content_type,
        llm_provider=llm_provider,
        llm_model=llm_model,
    )
    
    # Read file content
    content = await file.read()
    file_size = len(content)
    
    # Validate the file
    is_valid, error_message = validate_uploaded_file(
        filename=file.filename or "",
        content_type=file.content_type or "",
        file_size=file_size,
    )
    
    if not is_valid:
        logger.warning("file_validation_failed", error=error_message)
        raise HTTPException(status_code=400, detail=error_message)
    
    # Get file extension
    filename = file.filename or "unknown"
    ext = os.path.splitext(filename)[1].lower()
    
    # Save to temp file for conversion
    temp_file_path = None
    try:
        temp_file_path = await FileConversionService.save_upload_to_temp(content, ext)
        logger.info("uploaded_file_saved", temp_file_path=temp_file_path)
        
        # Convert to markdown
        try:
            markdown_content = FileConversionService.convert_to_markdown(temp_file_path)
            logger.info("file_converted_to_markdown", content_length=len(markdown_content))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except FileNotFoundError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as exc:
            logger.exception("file_conversion_failed", error=str(exc))
            raise HTTPException(status_code=500, detail=f"File conversion failed: {str(exc)}")
        
        # Stream the response
        base_filename = os.path.splitext(filename)[0]
        
        return StreamingResponse(
            _stream_conversion(base_filename, markdown_content, llm_provider, llm_model),
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "Transfer-Encoding": "chunked",
                "X-Content-Type-Options": "nosniff",
            },
        )
    
    finally:
        # Clean up temp file
        if temp_file_path:
            FileConversionService.cleanup_temp_file(temp_file_path)


@router.post(
    "/convert-to-markdown",
    response_model=dict,
    responses={
        400: {"model": ConversionError},
        500: {"model": ConversionError},
    },
)
async def convert_to_markdown(
    file: UploadFile = File(..., description="Document file to convert"),
) -> dict:
    """
    Convert a document to markdown format.
    
    This endpoint only converts to markdown without LLM transformation.
    Useful for previewing or debugging the conversion process.
    
    Returns the raw markdown content as JSON.
    """
    logger.info("markdown_conversion_requested", filename=file.filename)
    
    # Read file content
    content = await file.read()
    file_size = len(content)
    
    # Validate the file
    is_valid, error_message = validate_uploaded_file(
        filename=file.filename or "",
        content_type=file.content_type or "",
        file_size=file_size,
    )
    
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_message)
    
    # Get file extension
    filename = file.filename or "unknown"
    ext = os.path.splitext(filename)[1].lower()
    
    # Save to temp file for conversion
    temp_file_path = None
    try:
        temp_file_path = await FileConversionService.save_upload_to_temp(content, ext)
        
        # Convert to markdown
        try:
            markdown_content = FileConversionService.convert_to_markdown(temp_file_path)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as exc:
            logger.exception("markdown_conversion_failed", error=str(exc))
            raise HTTPException(status_code=500, detail=f"Conversion failed: {str(exc)}")
        
        return {
            "success": True,
            "filename": filename,
            "content_length": len(markdown_content),
            "markdown": markdown_content,
        }
    
    finally:
        if temp_file_path:
            FileConversionService.cleanup_temp_file(temp_file_path)

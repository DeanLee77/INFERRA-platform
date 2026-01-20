import ast
import os
import re
import tempfile
import json
from datetime import datetime

# Fix SSL context for macOS certificate issues
import ssl

import openai
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

from openai import OpenAI
# import fitz  # PyMuPDF for PDFs
# import docx  # python-docx for Word (.docx)
# import textract  # for old .doc
import pypandoc, uuid, time, random
from pathlib import Path
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
from typing import Tuple, Generator
from project.loggers import Logger
from dotenv import load_dotenv


logging: Logger = Logger.get_logger(__name__)
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path=dotenv_path)

OPENAI_CLIENT = None
LLM_MODEL = None
TIME_OUT = None
# Initialize OpenAI client once for reuse across requests
def get_openai_client():
    global OPENAI_CLIENT
    global LLM_MODEL
    global TIME_OUT
    
    if OPENAI_CLIENT is None or LLM_MODEL is None:
        # base_url = os.getenv("OPENROUTER_BASE_URL")
        # api_key = os.getenv("OPENROUTER_API_KEY")
        # TIME_OUT = float(os.getenv("OPENROUTER_TIMEOUT", "30"))
        # LLM_MODEL = os.getenv("OPENROUTER_MODEL")
        
        base_url = os.getenv("ZAI_BASE_URL")
        api_key = os.getenv("ZAI_API_KEY")
        TIME_OUT = float(os.getenv("LLM_TIMEOUT", "30"))
        LLM_MODEL = os.getenv("ZAI_MODEL")

        if not base_url or not api_key or not LLM_MODEL:
            raise ValueError("OPENROUTER_BASE_URL and OPENROUTER_API_KEY and LLM_MODEL must be set in .env file")
        OPENAI_CLIENT = OpenAI(
            base_url=base_url,
            api_key=api_key
        )

    return OPENAI_CLIENT

ALLOWED_EXTENSIONS_STR = os.getenv("ALLOWED_EXTENSIONS")
ALLOWED_EXTENSIONS = ast.literal_eval(ALLOWED_EXTENSIONS_STR) if os.getenv("ALLOWED_EXTENSIONS") else []

ALLOWED_MIMES_STR = os.getenv("ALLOWED_MIMES")
ALLOWED_MIMES = ast.literal_eval(ALLOWED_MIMES_STR) if os.getenv("ALLOWED_MIMES") else []
RULE_PROMPT_PATH = os.getenv("RULE_PROMPT_PATH", "nadia_prompt.md")

def demo_file_loading(fileName: str):
    demo_file = f'Nadia-{fileName}'
    if demo_file:
        with open(demo_file, "r") as file:
            return file.read()

def preprocess_text(text):
    """Preprocess text to fix special characters and mathematical expressions"""
    # Fix degree symbols and coordinates
    text = re.sub(r'(\d+)(\d+)([NSEW])', r'\1°\2′\3', text)
    text = re.sub(r'(\d+)(\d+)(\d+)(\d+)', r'\1°\2′\3°\4°', text)
    
    # Fix mathematical expressions
    text = re.sub(r' ', '(', text)
    text = re.sub(r'´', ')', text)
    text = re.sub(r'', '(', text)
    text = re.sub(r'', ')', text)
    
    # Fix other special characters
    replacements = {
        '': '(',          # Mathematical left parenthesis
        '': ')',          # Mathematical right parenthesis
        '´': ')',          # Mathematical right parenthesis
        '': '°',          # Degree symbol
        '': "'",          # Prime symbol → single quote
        '′': "'",          # Prime symbol → single quote
        '‴': "''",         # Double prime → double quotes
        '⁰': '0',          # Superscript zero
        '¹': '1',          # Superscript one
        '²': '2',          # Superscript two
        '³': '3',          # Superscript three
        '⁴': '4',          # Superscript four
        '⁵': '5',          # Superscript five
        '⁶': '6',          # Superscript six
        '⁷': '7',          # Superscript seven
        '⁸': '8',          # Superscript eight
        '⁹': '9'           # Superscript nine
    }
    
    for old, new in replacements.items():
        text = text.replace(old, new)
    
    # Fix mathematical notation
    text = re.sub(r'(\d+)\s*years?\s*´\s*\+\s*', r'(\1 years) + ', text)
    text = re.sub(r'(\d+)\s*years?\s*\+\s*', r'(\1 years) + ', text)
    
    return text

# ---------- File Validators ----------


def validate_file(uploaded_file, form_data) -> Tuple[bool, str]:
    """Validate file type by MIME and extension."""
    if not uploaded_file:
        return False, "No file provided"
    
    # Check filename extension
    filename = secure_filename(uploaded_file.filename)
    if not filename:
        return False, "Invalid filename"
    
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False, f"Unsupported extension: {ext}"
    
    # Check MIME type
    if uploaded_file.mimetype not in ALLOWED_MIMES:
        return False, "Unsupported MIME type"
    

    # Check if file is empty
    uploaded_file.seek(0, os.SEEK_END)
    size = uploaded_file.tell()
    uploaded_file.seek(0)
    if size == 0:
        return False, "Empty file"

    
    return True, "OK"

# ---------- Rule Guidance ----------

def load_nadia_guidance():
    """Load the NADIA guidance from a file"""
    try:
        with open(RULE_PROMPT_PATH, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        # Fallback to a minimal version if file not found
        return "NADIA prompt not found. Please provide the prompt."

def handle_pdf_file(file_path: str)  -> str:
    """Extract text from a PDF file using PyMuPDF"""
    try:
        doc = fitz.open(file_path)
        markdown_content = ""
        for page in doc:
            markdown_content += page.get_text() + "\n"
        doc.close()
        return markdown_content
    except:
        logging.error("Failed to open PDF file.")
        return f'[PDF extraction error: Unable to open PDF file.]'
    
# ---------- Convert PDF/Docx/Doc to md file ----------
def convert_file_to_markdown(file_path: str, file_type: str) -> str:
    """Convert a document file to Markdown with special character processing"""
    # Determine format
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.pdf':
        markdown_content = handle_pdf_file(file_path)
    elif ext == '.docx':
        pandoc_format = 'docx'
    elif ext == '.doc':
        pandoc_format = 'doc'
    else:
        raise ValueError("Unsupported file format")
    
    # Only use pypandoc for non-PDF files
    if ext != '.pdf':
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.md') as temp_md:
            try:
                pypandoc.convert_file(
                    file_path,
                    'markdown',
                    outputfile=temp_md.name,
                    format=pandoc_format,
                    extra_args=['--wrap=none']
                )
            except OSError:
                # SSL fix and pandoc download as before
                import ssl
                try:
                    _create_unverified_https_context = ssl._create_unverified_https_context
                except AttributeError:
                    pass
                else:
                    ssl._create_default_https_context = _create_unverified_https_context
                pypandoc.download_pandoc()
                pypandoc.convert_file(
                    file_path,
                    'markdown',
                    outputfile=temp_md.name,
                    format=pandoc_format,
                    extra_args=['--wrap=none']
                )
            temp_md_path = temp_md.name
        
        with open(temp_md_path, 'r', encoding='utf-8') as f:
            markdown_content = f.read()
        os.unlink(temp_md_path)
    
    # Apply special character fixes
    markdown_content = preprocess_text(markdown_content)
    return markdown_content


def transform_to_nadia_rules_stream_with_llm(markdown_content: str) -> Generator[str, None, None]:
    """Transform Markdown content to NADIA rule format using OpenRouter with streaming response"""
    global LLM_MODEL
    global TIME_OUT
    # Load the NADIA guidance document
    nadia_guidance = load_nadia_guidance()
    
    try:
        # Split markdown_content into manageable chunks logically
        chunks = split_content(markdown_content)
        total_chunks = len(chunks)
        
        generated_so_far = ""
        
        for idx, current_chunk in enumerate(chunks):
            chunk_index = idx + 1
            is_first = idx == 0
            previous_tail = generated_so_far[-500:] if not is_first else ""  # Use last 500 chars for context
            
            logging.info(f"Processing chunk {chunk_index}/{total_chunks} ({len(current_chunk)} chars)")
            
            # Create prompt for current chunk
            chunk_prompt = get_chunk_prompt(current_chunk, is_first, previous_tail, nadia_guidance)

            client = get_openai_client()
            timeout = TIME_OUT
            
            stream = None
            for attempt in range(3):
                try:
                    current_timeout = timeout * (2 ** attempt)
                    logging.info(f"API call attempt {attempt+1}/3 for chunk {chunk_index} with timeout={current_timeout}s")
                    
                    stream = client.chat.completions.create(
                        model=LLM_MODEL,
                        messages=[
                            {"role": "system", "content": "You are an expert NADIA rule engineer. Process document sections sequentially. Maintain state and continuity from previous output if provided. Complete rule structures before yielding."},
                            {"role": "user", "content": chunk_prompt}
                        ],
                        max_tokens=2000,
                        temperature=0.1,
                        timeout=current_timeout,
                        stream=True
                    )
                    break
                except Exception as e:
                    if attempt == 2:  # Last attempt
                        error_msg = f"API Error for chunk {chunk_index}: {str(e)}"
                        if "timed out" in str(e).lower():
                            error_msg += "\n\nDIAGNOSTIC: Skipping problematic chunk and continuing to next section."
                        yield error_msg
                        break
                    logging.warning(f"Chunk {chunk_index} request failed (attempt {attempt+1}/3): {str(e)}")
                    continue
            
            if stream is None:
                continue  # Skip to next chunk if all attempts failed
            
            # Stream response for this chunk and collect output
            chunk_output = ""
            for resp_chunk in stream:
                content = resp_chunk.choices[0].delta.content.trim()
                if content is not None:
                    content = resp_chunk.choices[0].delta.content
                    yield content
                    chunk_output += content
            
            generated_so_far += chunk_output
        
        # Signal completion after all chunks
        yield "\n\n[COMPLETED]"
    
    except openai.APIError as e:
        yield f"API Error: {str(e)}"
    except openai.RateLimitError as e:
        yield f"Rate Limit Error: {str(e)}"
    except Exception as e:
        yield f"Processing Error: {str(e)}"

def split_content_with_llm(content: str, max_size: int=8000) -> list[str]:
    """
    Split legislation text into chunks using LLM to ensure logical splits while keeping chunks under max_size.
    """
    global LLM_MODEL
    global TIME_OUT
    
    client = get_openai_client()
    chunks = []
    remaining_content = content
    request_id = str(uuid.uuid4())  # Unique ID for this splitting operation
    
    try:
        while remaining_content:
            # Create prompt for LLM to suggest logical split point
            split_prompt = f"""You are an expert in processing legal texts. Given the following legislation text, suggest a logical split point (in terms of character index) that:
                1. Keeps the chunk under {max_size} characters
                2. Preserves logical units (e.g., complete sections, clauses, or sentences)
                3. Avoids splitting in the middle of sentences or legal references

                Return only the suggested character index as an integer.

                Text:
                {remaining_content[:max_size+500]}  # Provide extra context for better splitting
            """
            for attempt in range(3):
                try:
                    response = client.chat.completions.create(
                        model=LLM_MODEL,
                        messages=[
                            {"role": "system", "content": "You are an expert in legal text analysis. Provide only a single integer representing the suggested split point."},
                            {"role": "user", "content": split_prompt}
                        ],
                        max_tokens=10,
                        temperature=0.1,
                        timeout=TIME_OUT * (2 ** attempt)
                    )
                    split_index = int(response.choices[0].message.content.strip()) if response.choices[0].message.content.strip() != '' else 0
                    
                    # Validate split index
                    if 0 < split_index <= max_size and split_index <= len(remaining_content):
                        chunks.append(remaining_content[:split_index])
                        remaining_content = remaining_content[split_index:].lstrip()
                        logging.info(f"Chunk created at index {split_index}, {len(chunks)} chunks so far")
                        break
                    else:
                        # Fallback to simple character-based split if invalid index
                        split_index = min(max_size, len(remaining_content))
                        chunks.append(remaining_content[:split_index])
                        remaining_content = remaining_content[split_index:].lstrip()
                        logging.warning(f"Invalid split index from LLM, using fallback at {split_index}")
                        break
                except Exception as e:
                    if attempt == 2:
                        # Fallback to simple character-based split if all attempts fail
                        split_index = min(max_size, len(remaining_content))
                        chunks.append(remaining_content[:split_index])
                        remaining_content = remaining_content[split_index:].lstrip()
                        logging.error(f"Failed to get split point from LLM for request {request_id}: {str(e)}")
                        break
                    logging.warning(f"Attempt {attempt+1}/3 failed for request {request_id}: {str(e)}")
                    continue
            
            # If remaining content is small enough, add it as the final chunk
            if len(remaining_content) <= max_size:
                if remaining_content:
                    chunks.append(remaining_content)
                break
    
        logging.info(f"Successfully split content into {len(chunks)} chunks for request {request_id}")
        return chunks
    
    except Exception as e:
        logging.error(f"Error splitting content for request {request_id}: {str(e)}")
        # Fallback: split by max_size if LLM fails entirely
        chunks = [content[i:i+max_size] for i in range(0, len(content), max_size)]
        return chunks
    
def is_table_line(line: str) -> bool:
    """Detect table rows in legislation (no separator lines)"""
    line = line.strip()
    
    # Must have pipe characters and be reasonably long
    if line.count('|') >= 2 and len(line) > 20:
        # Check for common table patterns in this legislation:
        # - Numbers, months, years, dollar amounts
        # - Column headers like "Period", "Column 1", etc.
        if re.search(r'\d+|month|year|dollar|\$|Column\s+\d+|Period', line, re.IGNORECASE):
            return True
            
        # Check if it has multiple cells with plausible content
        cells = [cell.strip() for cell in line.split('|') if cell.strip()]
        if len(cells) >= 2 and all(len(cell) > 3 for cell in cells[:2]):
            return True
    
    return False

def find_safe_split_point(chunk_lines: list[str]) -> int:
    """Find split point that preserves table context"""
    # Look backward for safe boundaries
    for i in range(len(chunk_lines) - 1, -1, -1):
        line = chunk_lines[i].strip()
        
        # Never split within a table reference
        if re.search(r'table|Column\s+\d+', line, re.IGNORECASE):
            continue  # Keep searching for earlier boundary
        
        # Never split mid-definition that references a table
        if i > 0 and re.search(r'following\s+table', chunk_lines[i-1], re.IGNORECASE):
            continue
        
        # Top-level section breaks (safest)
        if re.match(r'(Section|Part|Division|Clause)\s+', line, re.IGNORECASE):
            return i
        
        # Paragraph breaks
        if not line:
            return i + 1
        
        # Clause boundaries
        if re.match(r'\(\d+\)\s*$', line):  # End of numbered clause
            return i + 1
        if re.match(r'\([a-z]\)\s*$', line.lower()):  # End of lettered clause
            return i + 1
    
    # No safe point found - force split at 80% but preserve tables
    return max(1, int(len(chunk_lines) * 0.8))

def is_table_reference(line: str) -> bool:
    """Detect text that references a table"""
    return bool(re.search(r'table|Column\s+\d+|following\s+table|set\s+out\s+in', line, re.IGNORECASE))


def split_content(content: str, max_size: int = 7500) -> list[str]:
    """
    Split messy, real-world legislation text into semantically coherent chunks.
    Extracts logical units (e.g., sections, parts, schedules, tables) using regex patterns and line-by-line processing.
    Treats Markdown tables as indivisible units where possible.
    Groups units into chunks without exceeding max_size.
    If a single unit exceeds max_size, splits it internally at safe boundaries.
    Handles Markdown and preserves structure.
    """
    # Normalize line endings and fix common spacing issues
    content = re.sub(r'\r\n?', '\n', content)
    content = re.sub(r' {2,}', ' ', content)  # Collapse multiple spaces

    # Enhanced insertion of newlines for better structure detection
    content = re.sub(r'(?<!^)(#+\s)', r'\n\n\1', content)  # Before Markdown headings
    content = re.sub(r'(Section\s+\d+[A-Z]*\s*—\s*[^\n]*)', r'\n\n\1\n', content)  # Section headers
    content = re.sub(r'(Part\s+[IVX\d]+—[^\n]*)', r'\n\n\1\n', content)  # Part headers
    content = re.sub(r'(Division\s+\d+[^\n]*)', r'\n\n\1\n', content)  # Division headers
    content = re.sub(r'(Schedule\s+\d+[^\n]*)', r'\n\n\1\n', content)  # Schedule headers
    content = re.sub(r'(Clause\s+\d+[^\n]*)', r'\n\n\1\n', content)  # Clause headers
    content = re.sub(r'(Endnote\s+\d+[^\n]*)', r'\n\n\1\n', content)  # Endnote headers
    content = re.sub(r'(Note:\s*[^\n]*)', r'\n\n\1\n', content)  # Notes
    content = re.sub(r'(Example\s*\d*:\s*[^\n]*)', r'\n\n\1\n', content)  # Examples
    content = re.sub(r'(?<=\n)---(?=\n)', r'\n---\n', content)  # Ensure separators are isolated

    # Define patterns for logical unit boundaries (starts of major sections)
    unit_patterns = [
        r'^#+\s',  # Markdown headings like #, ##, ###
        r'^Section\s+\d+[A-Z]*\s*—',  # Section X — Title
        r'^Part\s+[IVX\d]+—',  # Part X—Title
        r'^Division\s+\d+',  # Division X
        r'^Schedule\s+\d+',  # Schedule X
        r'^Clause\s+\d+',  # Clause X
        r'^Endnote\s+\d+',  # Endnote X
        r'^Note:',  # Note:
        r'^Example\s*\d*:',  # Example:
        r'^---\s*$',  # Horizontal rules
    ]
    unit_regex = re.compile('|'.join(unit_patterns), re.MULTILINE | re.IGNORECASE)

    # Split into lines for processing
    lines = content.split('\n')

    # Extract units, handling tables as special multi-line units
    units = []
    current_unit = []
    in_table = False
    last_pos = 0

    # Use unit_regex to find boundaries, but also check for tables
    matches = list(unit_regex.finditer(content))
    match_positions = [(m.start(), m.end()) for m in matches]
    i = 0  # Line index
    match_idx = 0  # Regex match index

    while i < len(lines):
        line = lines[i].strip()
        line_start = sum(len(l) + 1 for l in lines[:i])  # Approximate position in content

        # Detect table-related lines
        is_table_row = line.startswith('|') and line.endswith('|') and '|' in line[1:-1]
        is_table_separator = re.match(r'^\|[-|: ]*(\|[-|: ]*)*\|$', line) is not None

        # Check if current line matches a unit boundary
        is_unit_boundary = False
        if match_idx < len(match_positions):
            match_start, _ = match_positions[match_idx]
            if line_start <= match_start < line_start + len(lines[i]) + 1:
                is_unit_boundary = True
                match_idx += 1

        if is_table_row or is_table_separator:
            if not in_table:
                # Flush previous non-table unit if it exists
                if current_unit:
                    unit_text = '\n'.join(current_unit).strip()
                    if unit_text:
                        units.append(unit_text)
                    current_unit = []
                in_table = True
            current_unit.append(lines[i])
        else:
            if in_table:
                # Flush table unit if it has at least 2 lines (header + separator or row)
                if len(current_unit) >= 2:
                    unit_text = '\n'.join(current_unit).strip()
                    if unit_text:
                        units.append(unit_text)
                current_unit = []
                in_table = False
            elif is_unit_boundary and current_unit:
                # Flush previous unit at regex-detected boundary
                unit_text = '\n'.join(current_unit).strip()
                if unit_text:
                    units.append(unit_text)
                current_unit = [lines[i]]
            else:
                current_unit.append(lines[i])
        i += 1

    # Flush final unit
    if current_unit:
        unit_text = '\n'.join(current_unit).strip()
        if unit_text:
            units.append(unit_text)

    # Group units into chunks without exceeding max_size
    chunks = []
    current_chunk_units = []
    current_len = 0

    for unit in units:
        unit_len = len(unit) + 2  # +2 for '\n\n' separator

        if current_len + unit_len > max_size and current_chunk_units:
            # Flush current chunk
            chunks.append('\n\n'.join(current_chunk_units).strip())
            current_chunk_units = []
            current_len = 0

        if unit_len > max_size:
            # Rare case: single unit too large; split internally
            internal_chunks = _split_large_unit(unit, max_size)
            chunks.extend(internal_chunks)
        else:
            current_chunk_units.append(unit)
            current_len += unit_len

    # Add final chunk
    if current_chunk_units:
        chunks.append('\n\n'.join(current_chunk_units).strip())

    return [c for c in chunks if c.strip()]

def _split_large_unit(unit: str, max_size: int) -> list[str]:
    """
    Helper to split a large logical unit (e.g., long section or table) at safe internal boundaries.
    For tables, attempts to split by groups of rows if possible.
    Falls back to paragraph or clause ends.
    """
    lines = unit.split('\n')
    sub_chunks = []
    current_sub = []
    current_sub_len = 0

    # Check if this unit looks like a table
    is_table = any(l.strip().startswith('|') for l in lines)

    i = 0
    while i < len(lines):
        line = lines[i]
        line_len = len(line) + 1

        if current_sub_len + line_len > max_size and current_sub:
            # Look backward for safe split in the large unit
            split_point = None
            for j in range(len(current_sub) - 1, -1, -1):
                prev_line = current_sub[j].strip()
                if not prev_line:  # Empty line (paragraph break)
                    split_point = j + 1
                    break
                if re.match(r'^\(\d+\)$', prev_line) or re.match(r'^\([a-z]\)$', prev_line):  # Clause ends
                    split_point = j + 1
                    break
                if prev_line.endswith('.') or prev_line.endswith('!') or prev_line.endswith('?'):  # Sentence end
                    split_point = j + 1
                    break
                if is_table and re.match(r'^\|[-|: ]+(\|[-|: ]+)*\|$', prev_line):  # After table separator
                    split_point = j + 1
                    break
                if is_table and prev_line.startswith('|') and prev_line.endswith('|'):  # After table row
                    split_point = j + 1
                    break

            if split_point is None:
                split_point = len(current_sub)  # Force split

            sub_text = '\n'.join(current_sub[:split_point]).strip()
            if sub_text:
                sub_chunks.append(sub_text)

            # Carry over
            current_sub = current_sub[split_point:]
            current_sub_len = sum(len(l) + 1 for l in current_sub)
        else:
            current_sub.append(line)
            current_sub_len += line_len
            i += 1

    # Final sub-chunk
    if current_sub:
        final_sub = '\n'.join(current_sub).strip()
        if final_sub:
            sub_chunks.append(final_sub)

    return sub_chunks


def get_chunk_prompt(
    chunk: str,
    is_first: bool,
    previous_tail: str,
    nadia_guidance: str
) -> str:
    """
    Generate the prompt for a specific chunk, including continuity from previous output if applicable.
    """
    base_prompt = f"""{nadia_guidance}
    ---
    {chunk}

    IMPORTANT: Stream the rule set in chunks. Do NOT attempt to send the entire response at once.
    Maintain valid NADIA syntax in each chunk. Do NOT omit any content."""
        
    if is_first:
        return base_prompt
    else:
        continuation = f"""Continue the NADIA rules transformation seamlessly from where the previous output left off.
                        The previous output ended with:
                        {previous_tail}

                        Ensure no repetition and maintain syntactic continuity.
                        """
    return f"""{continuation}
            {nadia_guidance}
            ---
            {chunk}

            IMPORTANT: Process only this section. Complete rule structures when possible. Stream output."""


def transform_to_nadia_rules_stream(fileName: str, markdown_content: str) -> Generator[str, None, None]:
    demo = os.getenv('DEMO')
    if demo:
        yield from string_streamer(fileName)
        yield "__STREAM_COMPLETE__\n"
        return
    else:
        try:
            chunks = split_content(markdown_content)
            total_chunks = len(chunks)
            generated_so_far = ""
            # Load the NADIA guidance document
            nadia_guidance = load_nadia_guidance()
            transfer_chunk_to_file(chunks)

            for idx, current_chunk in enumerate(chunks):
                chunk_index = idx + 1
                is_first = idx == 0
                previous_tail = generated_so_far[-500:] if not is_first else ""  # Use last 500 chars for context
                
                logging.info(f"Processing chunk {chunk_index}/{total_chunks} ({len(current_chunk)} chars)")
                
                # Create prompt for current chunk
                chunk_prompt = get_chunk_prompt(current_chunk, is_first, previous_tail, nadia_guidance)

                client = get_openai_client()
                timeout = TIME_OUT
                
                stream = None
                for attempt in range(3):
                    try:
                        current_timeout = timeout * (2 ** attempt)
                        logging.info(f"API call attempt {attempt+1}/3 for chunk {chunk_index} with timeout={current_timeout}s")
                        
                        stream = client.chat.completions.create(
                            model=LLM_MODEL,
                            messages=[
                                {"role": "system", "content": "You are an expert NADIA rule engineer. Process document sections sequentially. Maintain state and continuity from previous output if provided. Complete rule structures before yielding."},
                                {"role": "user", "content": chunk_prompt}
                            ],
                            max_tokens=2000,
                            temperature=0.1,
                            timeout=current_timeout,
                            stream=True
                        )
                        break
                    except Exception as e:
                        if attempt == 2:  # Last attempt
                            error_msg = f"API Error for chunk {chunk_index}: {str(e)}"
                            if "timed out" in str(e).lower():
                                error_msg += "\n\nDIAGNOSTIC: Skipping problematic chunk and continuing to next section."
                            yield error_msg
                            break
                        logging.warning(f"Chunk {chunk_index} request failed (attempt {attempt+1}/3): {str(e)}")
                        continue

                if stream is None:
                    error_msg = f"[ERROR] Skipping chunk {idx+1} due to repeated API failures."
                    yield error_msg + "\n"
                    continue

                chunk_output = ""
                for resp_chunk in stream:
                    content = resp_chunk.choices[0].delta.content
                    if content is not None:
                        yield content
                        chunk_output += content

                generated_so_far += chunk_output

            yield "\n__STREAM_COMPLETE__\n"

        except Exception as e:
            yield f"[FATAL_ERROR] {str(e)}\n"


def transfer_chunk_to_file(chunk_array: list[str]):
    for i, chunk in enumerate(chunk_array, start=1):
        filename = f"chunk_{i}.txt"
        with open(filename, 'w', encoding='utf-8') as file:
            file.write(chunk)
        print(f"Created file: {filename}")

def string_streamer(fileName: str) -> Generator[str, None, None]:
    chunk_size = 1024
    demo_file = demo_file_loading(fileName)
    for i in range(0, len(demo_file), chunk_size):
        yield demo_file[i:i + chunk_size]
        time.sleep(random.uniform(0.8, 1.5))  # Random delay between 0.1 and 0.5 seconds for streaming simulation effect

class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj: any) -> any:
        # Handle datetime objects
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()  # Serialize to ISO 8601 format
        # Handle custom objects generically
        if hasattr(obj, 'to_dict') and callable(getattr(obj, 'to_dict')):
            return obj.to_dict()
        elif hasattr(obj, 'to_json') and callable(getattr(obj, 'to_json')):
            return obj.to_json()
        elif hasattr(obj, '__dict__'):
            # Recursively serialize objects with __dict__
            return {key: self.default(value) for key, value in vars(obj).items()}
        try:
            # Try to convert to a JSON-serializable type
            return json.JSONEncoder.default(self, obj)
        except TypeError:
            # Fallback to string representation
            return str(obj)
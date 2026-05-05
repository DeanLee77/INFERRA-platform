import os
import time
import random
from typing import Generator

from .client import LLMClient
from .text_splitter import split_content
from src.shared.loggers import Logger
from src.config import settings

_logger: Logger = Logger.get_logger(__name__)


def load_inferra_guidance() -> str:
    try:
        with open(settings.RULE_PROMPT_PATH, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return "INFERRA prompt not found. Please provide the prompt."


def get_chunk_prompt(chunk: str, is_first: bool, previous_tail: str, inferra_guidance: str) -> str:
    base_prompt = f"""{inferra_guidance}
---
{chunk}

IMPORTANT: Stream the rule set in chunks. Do NOT attempt to send the entire response at once.
Maintain valid INFERRA syntax in each chunk. Do NOT omit any content."""
    if is_first:
        return base_prompt
    continuation = f"""Continue the INFERRA rules transformation seamlessly from where the previous output left off.
The previous output ended with:
{previous_tail}

Ensure no repetition and maintain syntactic continuity.
"""
    return f"""{continuation}
{inferra_guidance}
---
{chunk}

IMPORTANT: Process only this section. Complete rule structures when possible. Stream output."""


def transform_to_inferra_rules_stream(file_name: str, markdown_content: str) -> Generator[str, None, None]:
    demo = settings.DEMO
    if demo:
        yield from _string_streamer(file_name)
        yield "__STREAM_COMPLETE__\n"
        return

    try:
        chunks = split_content(markdown_content)
        total_chunks = len(chunks)
        generated_so_far = ""
        inferra_guidance = load_inferra_guidance()

        llm = LLMClient()
        if llm.client is None:
            yield "[ERROR] LLM client not configured\n"
            return

        for idx, current_chunk in enumerate(chunks):
            chunk_index = idx + 1
            is_first = idx == 0
            previous_tail = generated_so_far[-500:] if not is_first else ""

            _logger.info(f"Processing chunk {chunk_index}/{total_chunks} ({len(current_chunk)} chars)")
            chunk_prompt = get_chunk_prompt(current_chunk, is_first, previous_tail, inferra_guidance)

            stream = None
            for attempt in range(3):
                try:
                    current_timeout = llm.timeout * (2 ** attempt)
                    _logger.info(f"API call attempt {attempt+1}/3 for chunk {chunk_index} with timeout={current_timeout}s")

                    stream = llm.client.chat.completions.create(
                        model=llm.model,
                        messages=[
                            {"role": "system", "content": "You are an expert INFERRA rule engineer. Process document sections sequentially. Maintain state and continuity from previous output if provided. Complete rule structures before yielding."},
                            {"role": "user", "content": chunk_prompt}
                        ],
                        max_tokens=2000,
                        temperature=0.1,
                        timeout=current_timeout,
                        stream=True
                    )
                    break
                except Exception as e:
                    if attempt == 2:
                        error_msg = f"API Error for chunk {chunk_index}: {str(e)}"
                        if "timed out" in str(e).lower():
                            error_msg += "\n\nDIAGNOSTIC: Skipping problematic chunk and continuing to next section."
                        yield error_msg
                        break
                    _logger.warning(f"Chunk {chunk_index} request failed (attempt {attempt+1}/3): {str(e)}")
                    continue

            if stream is None:
                yield f"[ERROR] Skipping chunk {idx+1} due to repeated API failures.\n"
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


def _demo_file_loading(file_name: str) -> str:
    demo_file = f"Inferra-{file_name}"
    with open(demo_file, "r", encoding="utf-8") as file:
        return file.read()


def _string_streamer(file_name: str) -> Generator[str, None, None]:
    chunk_size = 1024
    demo_file = _demo_file_loading(file_name)
    for i in range(0, len(demo_file), chunk_size):
        yield demo_file[i:i + chunk_size]
        time.sleep(random.uniform(0.8, 1.5))

import time
from unittest.mock import MagicMock, patch, mock_open

import pytest

from src.adapters.outbound.llm.streamer import (
    load_inferra_guidance,
    get_chunk_prompt,
    transform_to_inferra_rules_stream,
    _demo_file_loading,
    _string_streamer,
)


class TestLoadInferraGuidance:
    @patch("builtins.open", mock_open(read_data="INFERRA guidance text"))
    def test_loads_guidance(self):
        with patch("src.adapters.outbound.llm.streamer.settings") as mock_settings:
            mock_settings.RULE_PROMPT_PATH = "prompt.md"
            result = load_inferra_guidance()
            assert result == "INFERRA guidance text"

    @patch("builtins.open", side_effect=FileNotFoundError)
    def test_file_not_found_returns_fallback(self, mock_file):
        with patch("src.adapters.outbound.llm.streamer.settings") as mock_settings:
            mock_settings.RULE_PROMPT_PATH = "missing.md"
            result = load_inferra_guidance()
            assert "not found" in result


class TestGetChunkPrompt:
    def test_first_chunk(self):
        result = get_chunk_prompt("chunk text", is_first=True, previous_tail="", inferra_guidance="guide")
        assert "guide" in result
        assert "chunk text" in result
        assert "previous output" not in result.lower()

    def test_continuation_chunk(self):
        result = get_chunk_prompt("chunk text", is_first=False, previous_tail="tail end", inferra_guidance="guide")
        assert "tail end" in result
        assert "guide" in result
        assert "chunk text" in result
        assert "Continue" in result


class TestTransformToInferraRulesStream:
    @patch("src.adapters.outbound.llm.streamer.settings")
    def test_demo_mode_yields_stream(self, mock_settings):
        mock_settings.DEMO = "true"
        with patch("src.adapters.outbound.llm.streamer._string_streamer") as mock_streamer:
            mock_streamer.return_value = iter(["chunk1", "chunk2"])
            chunks = list(transform_to_inferra_rules_stream("test_file", "content"))
            assert any("chunk1" in c for c in chunks) or any("chunk2" in c for c in chunks)

    @patch("src.adapters.outbound.llm.streamer.settings")
    @patch("src.adapters.outbound.llm.streamer.split_content")
    @patch("src.adapters.outbound.llm.streamer.LLMClient")
    @patch("src.adapters.outbound.llm.streamer.load_inferra_guidance")
    def test_client_not_configured(self, mock_guidance, mock_llm, mock_split, mock_settings):
        mock_settings.DEMO = None
        mock_guidance.return_value = "guidance"
        mock_split.return_value = ["chunk1"]
        mock_client_instance = MagicMock()
        mock_client_instance.client = None
        mock_llm.return_value = mock_client_instance
        chunks = list(transform_to_inferra_rules_stream("file", "content"))
        assert any("[ERROR]" in c for c in chunks)

    @patch("src.adapters.outbound.llm.streamer.settings")
    @patch("src.adapters.outbound.llm.streamer.split_content")
    @patch("src.adapters.outbound.llm.streamer.LLMClient")
    @patch("src.adapters.outbound.llm.streamer.load_inferra_guidance")
    def test_successful_stream(self, mock_guidance, mock_llm, mock_split, mock_settings):
        mock_settings.DEMO = None
        mock_guidance.return_value = "guidance"
        mock_split.return_value = ["chunk1"]
        mock_client_instance = MagicMock()
        mock_client_instance.client = MagicMock()
        mock_client_instance.model = "test-model"
        mock_client_instance.timeout = 30.0
        mock_llm.return_value = mock_client_instance
        mock_resp_chunk = MagicMock()
        mock_resp_chunk.choices = [MagicMock()]
        mock_resp_chunk.choices[0].delta.content = "output text"
        mock_stream = MagicMock()
        mock_stream.__iter__ = lambda self: iter([mock_resp_chunk])
        mock_client_instance.client.chat.completions.create.return_value = mock_stream
        chunks = list(transform_to_inferra_rules_stream("file", "content"))
        assert any("output text" in c for c in chunks)
        assert any("__STREAM_COMPLETE__" in c for c in chunks)

    @patch("src.adapters.outbound.llm.streamer.settings")
    @patch("src.adapters.outbound.llm.streamer.split_content")
    @patch("src.adapters.outbound.llm.streamer.LLMClient")
    @patch("src.adapters.outbound.llm.streamer.load_inferra_guidance")
    def test_api_failure_all_retries(self, mock_guidance, mock_llm, mock_split, mock_settings):
        mock_settings.DEMO = None
        mock_guidance.return_value = "guidance"
        mock_split.return_value = ["chunk1"]
        mock_client_instance = MagicMock()
        mock_client_instance.client = MagicMock()
        mock_client_instance.model = "test-model"
        mock_client_instance.timeout = 30.0
        mock_llm.return_value = mock_client_instance
        mock_client_instance.client.chat.completions.create.side_effect = Exception("API down")
        chunks = list(transform_to_inferra_rules_stream("file", "content"))
        assert any("[ERROR]" in c or "API Error" in c for c in chunks)

    @patch("src.adapters.outbound.llm.streamer.settings")
    @patch("src.adapters.outbound.llm.streamer.split_content")
    @patch("src.adapters.outbound.llm.streamer.LLMClient")
    @patch("src.adapters.outbound.llm.streamer.load_inferra_guidance")
    def test_api_timeout_diagnostic(self, mock_guidance, mock_llm, mock_split, mock_settings):
        mock_settings.DEMO = None
        mock_guidance.return_value = "guidance"
        mock_split.return_value = ["chunk1"]
        mock_client_instance = MagicMock()
        mock_client_instance.client = MagicMock()
        mock_client_instance.model = "test-model"
        mock_client_instance.timeout = 30.0
        mock_llm.return_value = mock_client_instance
        mock_client_instance.client.chat.completions.create.side_effect = Exception("Request timed out")
        chunks = list(transform_to_inferra_rules_stream("file", "content"))
        assert any("DIAGNOSTIC" in c for c in chunks)

    @patch("src.adapters.outbound.llm.streamer.settings")
    @patch("src.adapters.outbound.llm.streamer.split_content")
    @patch("src.adapters.outbound.llm.streamer.LLMClient")
    @patch("src.adapters.outbound.llm.streamer.load_inferra_guidance")
    def test_stream_none_after_retries(self, mock_guidance, mock_llm, mock_split, mock_settings):
        mock_settings.DEMO = None
        mock_guidance.return_value = "guidance"
        mock_split.return_value = ["chunk1", "chunk2"]
        mock_client_instance = MagicMock()
        mock_client_instance.client = MagicMock()
        mock_client_instance.model = "test-model"
        mock_client_instance.timeout = 30.0
        mock_llm.return_value = mock_client_instance
        mock_client_instance.client.chat.completions.create.side_effect = Exception("API down")
        chunks = list(transform_to_inferra_rules_stream("file", "content"))
        assert any("[ERROR]" in c or "Skipping" in c for c in chunks)

    @patch("src.adapters.outbound.llm.streamer.settings")
    @patch("src.adapters.outbound.llm.streamer.split_content")
    @patch("src.adapters.outbound.llm.streamer.LLMClient")
    @patch("src.adapters.outbound.llm.streamer.load_inferra_guidance")
    def test_fatal_error(self, mock_guidance, mock_llm, mock_split, mock_settings):
        mock_settings.DEMO = None
        mock_guidance.side_effect = RuntimeError("unexpected")
        chunks = list(transform_to_inferra_rules_stream("file", "content"))
        assert any("[FATAL_ERROR]" in c for c in chunks)

    @patch("src.adapters.outbound.llm.streamer.settings")
    @patch("src.adapters.outbound.llm.streamer.split_content")
    @patch("src.adapters.outbound.llm.streamer.LLMClient")
    @patch("src.adapters.outbound.llm.streamer.load_inferra_guidance")
    def test_none_content_in_stream(self, mock_guidance, mock_llm, mock_split, mock_settings):
        mock_settings.DEMO = None
        mock_guidance.return_value = "guidance"
        mock_split.return_value = ["chunk1"]
        mock_client_instance = MagicMock()
        mock_client_instance.client = MagicMock()
        mock_client_instance.model = "test-model"
        mock_client_instance.timeout = 30.0
        mock_llm.return_value = mock_client_instance
        mock_resp_chunk = MagicMock()
        mock_resp_chunk.choices = [MagicMock()]
        mock_resp_chunk.choices[0].delta.content = None
        mock_stream = MagicMock()
        mock_stream.__iter__ = lambda self: iter([mock_resp_chunk])
        mock_client_instance.client.chat.completions.create.return_value = mock_stream
        chunks = list(transform_to_inferra_rules_stream("file", "content"))
        has_complete = any("__STREAM_COMPLETE__" in c for c in chunks)
        assert has_complete


class TestDemoFileLoading:
    @patch("builtins.open", mock_open(read_data="demo content"))
    def test_loads_file(self):
        result = _demo_file_loading("test_file")
        assert result == "demo content"


class TestStringStreamer:
    @patch("src.adapters.outbound.llm.streamer._demo_file_loading")
    @patch("src.adapters.outbound.llm.streamer.time")
    def test_yields_chunks(self, mock_time, mock_load):
        mock_load.return_value = "a" * 2048
        mock_time.sleep = MagicMock()
        chunks = list(_string_streamer("file"))
        assert len(chunks) >= 2
        assert "".join(chunks) == "a" * 2048

    @patch("src.adapters.outbound.llm.streamer._demo_file_loading")
    @patch("src.adapters.outbound.llm.streamer.time")
    def test_small_file_single_chunk(self, mock_time, mock_load):
        mock_load.return_value = "small"
        mock_time.sleep = MagicMock()
        chunks = list(_string_streamer("file"))
        assert len(chunks) == 1
        assert chunks[0] == "small"

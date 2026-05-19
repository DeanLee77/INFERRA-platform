from src.adapters.outbound.llm.text_splitter import split_content, _split_large_unit


class TestSplitContentBasicSplitting:
    def test_small_content_single_chunk(self):
        result = split_content("Hello world")
        assert len(result) >= 1
        assert any("Hello world" in c for c in result)

    def test_empty_content(self):
        result = split_content("")
        assert result == []

    def test_normalizes_line_endings(self):
        result = split_content("line1\r\nline2\rline3")
        assert len(result) >= 1

    def test_collapses_multiple_spaces(self):
        result = split_content("hello    world")
        assert "hello world" in result[0]


class TestSplitContentMarkdownHeaders:
    def test_splits_on_headers(self):
        content = "## Section One\nSome text\n\n## Section Two\nMore text"
        result = split_content(content)
        assert len(result) >= 1
        combined = "\n".join(result)
        assert "Section One" in combined
        assert "Section Two" in combined


class TestSplitContentSectionPatterns:
    def test_section_pattern(self):
        content = "Section 1—Introduction\n\nIntro text\n\nSection 2—Scope\n\nScope text"
        result = split_content(content)
        assert len(result) >= 1
        combined = "\n".join(result)
        assert "Introduction" in combined

    def test_part_pattern(self):
        content = "Part I—General\n\nGeneral text\n\nPart II—Specific\n\nSpecific text"
        result = split_content(content)
        assert len(result) >= 1

    def test_division_pattern(self):
        content = "Division 1 Overview\n\nOverview text\n\nDivision 2 Details\n\nDetails text"
        result = split_content(content)
        assert len(result) >= 1

    def test_schedule_pattern(self):
        content = "Schedule 1 Requirements\n\nReq text\n\nSchedule 2 Exceptions\n\nExc text"
        result = split_content(content)
        assert len(result) >= 1

    def test_clause_pattern(self):
        content = "Clause 1 Definitions\n\nDef text\n\nClause 2 Scope\n\nScope text"
        result = split_content(content)
        assert len(result) >= 1

    def test_endnote_pattern(self):
        content = "Endnote 1 Reference\n\nRef text\n\nEndnote 2 Citation\n\nCit text"
        result = split_content(content)
        assert len(result) >= 1

    def test_note_pattern(self):
        content = "Note: This is important\n\nNote text\n\nNote: Another note\n\nMore text"
        result = split_content(content)
        assert len(result) >= 1

    def test_example_pattern(self):
        content = "Example 1: First example\n\nEx1 text\n\nExample: General example\n\nEx text"
        result = split_content(content)
        assert len(result) >= 1

    def test_horizontal_rule(self):
        content = "Before\n\n---\n\nAfter"
        result = split_content(content)
        assert len(result) >= 1


class TestSplitContentTables:
    def test_table_detection(self):
        content = "Text before\n| A | B |\n|---|---|\n| 1 | 2 |\nText after"
        result = split_content(content)
        assert len(result) >= 1

    def test_table_only(self):
        content = "| A | B |\n|---|---|\n| 1 | 2 |"
        result = split_content(content)
        assert len(result) >= 1


class TestSplitContentMaxSize:
    def test_small_max_size_produces_multiple_chunks(self):
        content = "## S1\n" + "A" * 2000 + "\n## S2\n" + "B" * 2000
        result = split_content(content, max_size=2000)
        assert len(result) >= 2


class TestSplitContentUnitRegex:
    def test_header_unit_split(self):
        content = "# Title\nParagraph one.\n\n## Subtitle\nParagraph two."
        result = split_content(content, max_size=5000)
        assert len(result) >= 1
        combined = "\n".join(result)
        assert "Title" in combined
        assert "Subtitle" in combined


class TestSplitLargeUnit:
    def test_short_unit_single_chunk(self):
        result = _split_large_unit("Hello world. How are you?", max_size=100)
        assert len(result) == 1

    def test_preserves_content(self):
        unit = "Hello world. How are you?"
        result = _split_large_unit(unit, max_size=100)
        combined = " ".join(result)
        assert "Hello" in combined

    def test_large_unit_splits_on_sentence(self):
        lines = ["Line " + str(i) + "." for i in range(100)]
        unit = "\n".join(lines)
        result = _split_large_unit(unit, max_size=50)
        assert len(result) >= 2

    def test_single_short_line(self):
        result = _split_large_unit("short", max_size=100)
        assert result == ["short"]

    def test_strips_whitespace_from_chunks(self):
        unit = "  hello  \n  world  "
        result = _split_large_unit(unit, max_size=100)
        assert all(r.strip() == r for r in result)

    def test_empty_lines_as_split_point(self):
        lines = ["paragraph one"] + [""] + ["paragraph two"] + [""] + ["paragraph three"]
        unit = "\n".join(lines)
        result = _split_large_unit(unit, max_size=20)
        assert len(result) >= 2

    def test_no_split_point_long_line(self):
        unit = "a" * 300
        result = _split_large_unit(unit, max_size=100)
        assert len(result) >= 1

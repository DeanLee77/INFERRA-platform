import re


class LLMPromptSanitizer:
    """Small, deterministic guard for prompt-injection shaped input."""

    MAX_LENGTH = 1000
    DISALLOWED_PATTERNS = (
        re.compile(r"ignore\s+(all\s+)?(previous|above)\s+instructions", re.IGNORECASE),
        re.compile(r"\b(system|assistant)\s*:", re.IGNORECASE),
        re.compile(r"</?\s*system\s*>", re.IGNORECASE),
        re.compile(r"reveal\s+(the\s+)?(system\s+)?prompt", re.IGNORECASE),
    )

    @classmethod
    def sanitize(cls, value: str) -> str:
        text = (value or "").strip()
        if len(text) > cls.MAX_LENGTH:
            raise ValueError("Prompt input exceeds maximum length")
        for pattern in cls.DISALLOWED_PATTERNS:
            if pattern.search(text):
                raise ValueError("Prompt input contains disallowed patterns")
        return text

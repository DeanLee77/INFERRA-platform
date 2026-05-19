from dataclasses import dataclass


@dataclass(frozen=True)
class ProvOTrace:
    session_id: str
    content: str
    format: str = "turtle"

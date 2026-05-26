from dataclasses import dataclass, field
from typing import Optional, List, Any, Dict

from src.domain.models.rule_file_payload import (
    decode_rule_file_graph_json,
    decode_rule_file_text,
)


@dataclass
class RuleEntity:
    rule_id: Optional[int] = None
    name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None


@dataclass
class RuleFileEntity:
    file_id: Optional[int] = None
    rule_id: Optional[int] = None
    files: Optional[bytes] = None

    def decode_files(self) -> str:
        if self.files is None:
            raise ValueError("No file content stored")
        return decode_rule_file_text(self.files)

    def decode_graph_json(self) -> Optional[str]:
        if self.files is None:
            raise ValueError("No file content stored")
        return decode_rule_file_graph_json(self.files)


@dataclass
class RuleHistoryEntity:
    history_id: Optional[int] = None
    rule_id: Optional[int] = None
    history: Optional[Dict[str, Any]] = None

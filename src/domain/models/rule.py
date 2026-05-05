from dataclasses import dataclass, field
from typing import Optional, List, Any, Dict


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
        return self.files.decode('utf-8')


@dataclass
class RuleHistoryEntity:
    history_id: Optional[int] = None
    rule_id: Optional[int] = None
    history: Optional[Dict[str, Any]] = None

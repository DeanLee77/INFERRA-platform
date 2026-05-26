from dataclasses import dataclass
from typing import Optional


@dataclass
class CreateFile:
    rule_name: str = ""
    rule_text: str = ""

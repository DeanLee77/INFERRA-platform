"""
PALOS Fact Values Package Initialization.
Defines the public API surface for fact value classes.
"""

from .fact_value import FactValue
from .fact_value_type import FactValueType

# Public Access Level: Explicitly define the public API surface
# Prevents internal implementation details from being accidentally imported
__all__ = [
    'FactValue',
    'FactValueType'
]
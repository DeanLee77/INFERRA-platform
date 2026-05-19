from enum import Enum


class FactSource(Enum):
    """Provenance tag for working-memory entries.

    ASSERTED: supplied by the user or treated as authoritative system input.
    INFERRED: derived by the rule engine or iterate conclusions.
    LEARNED: promoted from induction or learned rule evidence.
    HYPOTHETICAL: temporary abduction hypothesis.
    SEMANTIC: projected from an ontology / RDF source.
    """

    ASSERTED = "ASSERTED"
    INFERRED = "INFERRED"
    LEARNED = "LEARNED"
    HYPOTHETICAL = "HYPOTHETICAL"
    SEMANTIC = "SEMANTIC"

    @classmethod
    def from_value(cls, value: object) -> "FactSource":
        """Parse persisted fact-source values, defaulting unknown future values."""
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value))
        except ValueError:
            return cls.INFERRED

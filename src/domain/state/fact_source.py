from enum import Enum


class FactSource(Enum):
    """Provenance tag for working-memory entries.

    ASSERTED  — supplied by the user or treated as authoritative system input
    INFERRED  — derived by the rule engine or iterate conclusions
    SEMANTIC  — projected from an ontology / RDF source
    """

    ASSERTED = "ASSERTED"
    INFERRED = "INFERRED"
    LEARNED = "LEARNED"
    HYPOTHETICAL = "HYPOTHETICAL"
    SEMANTIC = "SEMANTIC"

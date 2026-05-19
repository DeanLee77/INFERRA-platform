from src.domain.state.fact_source import FactSource

__all__ = ["FactSource", "LayeredFactStore"]


def __getattr__(name):
    if name == "LayeredFactStore":
        from src.domain.state.layered_fact_store import LayeredFactStore

        return LayeredFactStore
    raise AttributeError(name)

# inferra-core

`inferra-core` is INFERRA's deterministic, infrastructure-independent Python
kernel. Version `0.1.1` is an internal pre-release distribution created during
the Platform extraction. It is not yet published to a public package registry.

The supported API remains the deliberately small `inferra_core` top-level
facade. P0.2a added fact and graph value types, immutable validation
diagnostics, evaluation-history values, and the engine's Core-owned abstract
ports. P0.2b adds runnable graph, node, token, parser, and deterministic
validation implementations under `inferra_core._internal`. The P0 security
correction replaces string-to-SymPy evaluation with a bounded, manually
interpreted INFERRA expression AST; declaration validation fails closed and
topological cycles raise a typed error. Those private names are extraction
scaffolding, not a stable consumer API. A narrow compile/validation facade and
Platform rewiring are required before the next implementation layer moves.

Core currently has no third-party runtime dependencies. It must not import
Platform, FastAPI, persistence, network, worker, product-extension, Structlog,
environment-feature-flag, or global deployment configuration code. Parser
node-ID collision tracking is caller-owned; validation caching is disabled
unless the host supplies a clock.

Build and test it independently from this directory:

```shell
python -m pip wheel --no-deps .
python -m pytest
```

Platform now hosts deterministic rule validation through the Core
implementation while supplying its own cache clock. Platform retains its
compatibility-heavy parser, nested iterate execution, and matrix adapters until
the immediate integration gate rewires the completed slice to a supported Core
compile/validation facade.

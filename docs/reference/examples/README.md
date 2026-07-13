# INFERRA Example Rule Sets

Example rule sets and authoring fixtures for INFERRA syntax and runtime features.

Authoring surfaces should load `authoring_catalog.json` from this directory when they need discoverable examples by feature. The catalog keeps the normal example-loading path stable while allowing examples to include multiple companion files, such as trigger policy JSON plus source and target rule sets.

## Discoverable Catalog

| File | Purpose |
|------|---------|
| `authoring_catalog.json` | Feature-tagged authoring catalog for UI/example discovery. |
| `triggers/` | Governed trigger policy examples with companion rule sets and trigger requests. |

## Reference Rule Corpora

The top-level `vea_*`, `mrca_*`, and `drca_*` text files are legislative-style rule-set fixtures used by validation, parsing, retrieval, and demo tests.

For the full INFERRA rule syntax reference, see [`../../INFERRA_Rule_Syntax_Dictionary.md`](../../INFERRA_Rule_Syntax_Dictionary.md).

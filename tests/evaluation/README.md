# Neuro-Symbolic Golden Cases

This harness is the first local regression suite for INFERRA's neuro-symbolic behavior. It intentionally uses synthetic fixtures, in-memory ontology triples, offline reference documents, and disabled optional reasoning routes so it can run without Docker, paid services, live LLM calls, vector stores, broad network access, or production data.

## Command

```powershell
python -m pytest tests/evaluation/test_neuro_symbolic_golden_cases.py
python -m pytest tests/evaluation/test_graphrag_retrieval_provenance.py
```

This heartbeat verified the command through the repo virtualenv:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/evaluation
```

Baseline on 2026-06-01: 12 passed in 2.42s.

The retrieval provenance harness can also emit its JSON report directly:

```powershell
.\.venv\Scripts\python.exe tests/evaluation/retrieval_provenance_harness.py
```

## Coverage

- Symbolic consistency: synthetic decision receipt outcomes stay aligned with fixture expectations, source labels, rule version, missing-evidence prompts, and sanitization flags.
- Retrieval provenance: in-memory ontology enrichment produces advisory `SEMANTIC` tags with subject/predicate/object provenance and does not override asserted facts.
- GraphRAG retrieval provenance: offline lexical golden cases over `docs/reference/examples/` and active docs report precision, recall, freshness, and provenance coverage from `retrieval_source_manifest.json`.
- Abstention: the reasoning router exposes `no_alternate_route` when deduction is stalled and optional routes are disabled or empty.
- Failure reporting: invalid fixture IDs fail loudly and list accepted golden-case IDs.
- Non-authority guard: unprovenanced retrieval is rejected from authoritative `ASSERTED` and `INFERRED` fact layers, and all retrieval results remain `evaluation_only_non_authoritative`.

## Known Gaps

- The suite measures offline GraphRAG fixture precision, recall, freshness, and provenance coverage only; it does not claim live GraphRAG quality.
- The suite does not enable external LLM providers or evaluate model answer quality.
- Synthetic decision receipts include a generated timestamp, so the test checks stable schema and contract fields rather than a byte-for-byte snapshot.
- User-facing explainability copy and trust cues are outside this harness and belong in the UX workflow.

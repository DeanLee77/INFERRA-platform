# SNOMED-MBS Integration — Gaps Analysis Across PLAN, GUIDE, and Codebase

> **Superseded:** 2026-07-14. This point-in-time analysis is retained for
> historical context only. Its feature-flag and implementation-existence claims
> must not be used as current guidance. Use `src/domain/state/feature_flags.py`,
> `IMPLEMENTATION_GUIDE.md`, and `docs/IMPLEMENTATION_STATUS.md` instead.
>
> **Date:** 2026-07-04
> **Analysis Target:** Three-way gap between:
> 1. `docs/archive/phase-plans/SNOMED_MBS_INTEGRATION_PLAN.md` (52KB — baseline reference plan)
> 2. `SNOMED_MBS_INTEGRATION_GUIDE.md` (62KB — implementation guide)
> 3. Actual `src/` codebase (implied claims from both documents)

---

## 0. Document Positioning

| Document | Role | Audience | Verdict |
|----------|------|----------|---------|
| **PLAN** (`docs/`) | Strategic architecture assessment: what the platform CAN do | Architects, CTO, platform evaluators | ✅ Accurate, well-verified against code |
| **GUIDE** (`root`) | Implementation cookbook: copy-paste adapters, routes, tests | Developers, integrators | ⚠️ Partially accurate, 22 references to non-existent code |
| **Codebase** (`src/`) | Ground truth | Runtime | ✅ Production ontology stack, no clinical adapters |

---

## 1. PLAN vs CODE — What the Plan Says vs Reality

### ✅ PLAN Claims — Verified Correct

| PLAN Claim | Code Verification |
|-----------|-------------------|
| `FusekiAdapter.execute_guarded_select()` exists | ✅ `fuseki_adapter.py:256` — SPARQL SELECT with timeout+retry |
| `OntologyIndex.class_ancestors()` BFS closure | ✅ `semantic_fact_enricher.py:657` — `rdfs:subClassOf + owl:equivalentClass` |
| `OntologyBindingResolver` exact-label match | ✅ `semantic_fact_enricher.py:181` — casefold label matching |
| `ProvOTraceGenerator` exists | ✅ `src/domain/trace/prov_o_trace_generator.py` |
| `SemanticFactEnricher` → FactSource.SEMANTIC layer | ✅ `semantic_fact_enricher.py` — tag derivation |
| `OntologyReasoner.materialize()` → FactSource.INFERRED | ✅ `ontology_reasoner.py` — flag-gated |
| `full_semantic_pilot` ontology profile | ✅ `inference.py:759` — valid profile name |
| Feature flags: all 4 ontology flags exist | ✅ `feature_flags.py` |
| IS-A traversal via `rdfs:subClassOf` | ✅ `OntologyIndex._closure()` |
| `owl:equivalentClass` bidirectional | ✅ `OntologyIndex.get_equivalent_classes()` |

### ⚠️ PLAN Claims — Minor Inaccuracies

| PLAN Claim | Correction |
|-----------|-----------|
| `/api/v1/ontology/decision-path` endpoint | Actual route is `POST /path/resolve` (still a decision-path resolver, just different URL) |
| `/api/v1/ontology/chat/query` endpoint | Actual route is `POST /chat/query` (under `/api/v1/ontology` prefix) |
| `./s-put http://localhost:3030/inferra/data?graph=X file.ttl` | `s-put` is Jena command-line tool, works but `curl -X POST` also works |
| `owl:equivalentClass` for MBS↔SNOMED mapping | `owl:` prefix is supported as data but not semantically by reasoner (infra only uses `owl:equivalentClass` in `OntologyIndex`) |

### ❌ PLAN Claims — Missing/Inaccurate vs CODE

| PLAN Claim | Real Status |
|-----------|-------------|
| "OWL 2 RL-aligned subset" | Per own disclaimers in `semantic_fact_enricher.py`: still limited subset, actual OWL 2 RL compliance not claimed |
| `SNOMED attribute traversal (HAS_FINDING_SITE, etc.)` "extend enricher for custom predicates" | PLAN correctly identifies this gap — enricher only handles built-in predicates (rdfs:subClassOf, rdf:type, rdfs:domain, etc.) |
| `RF2→RDF ETL pseudocode` | PLAN provides this — but it lives only in the PLAN, not in GUIDE or codebase |

### Key Strengths of PLAN over GUIDE

1. **RF2→RDF ETL pipeline pseudocode** — PLAN gives `sct2_Concept`, `sct2_Description`, `sct2_Relationship` parsing logic; GUIDE skips this entirely and talks about loading pre-converted RDF
2. **MBS-SNOMED Map Refset details** — PLAN explains `der2_cRefset_MBSMapFull_AU1000036.txt`; GUIDE has vague "crosswalk" with no refset reference
3. **Honest Assessment table** — PLAN has explicit ✅/⚠️/❌ tables; GUIDE scatters this across Quick Reference and Part 6
4. **SNOMED attribute traversal gap** — PLAN explicitly notes `SemanticFactEnricher` only tags built-in predicates; GUIDE never mentions this limitation
5. **Fuzzy label matching gap** — PLAN notes `OntologyBindingResolver` uses exact match; GUIDE doesn't warn about this
6. **NCTS API gap** — PLAN mentions missing NCTS adapter; GUIDE ignores real-time terminology server
7. **Scale warning** — PLAN warns `OntologyIndex` loads all triples in-memory for full SNOMED (400K concepts × ~1.5M relationships); GUIDE doesn't address this scalability constraint
8. **3-tier approach** — PLAN recommends subset→rule_integration→full_load progression; GUIDE has 5-phase but mixes schema design, adapter creation, and rule authoring into flat phases

---

## 2. GUIDE vs CODE — What the Guide Says vs Reality

### ✅ GUIDE Claims — Verified Correct

| GUIDE Claim | Code Verification |
|-------------|-------------------|
| FusekiAdapter for RDF storage | ✅ `fuseki_adapter.py` |
| INFERRA→RDF compiler | ✅ `inferra_to_rdf_compiler.py` |
| OntologyReasoner with `rdfs:subClassOf` closure | ✅ `ontology_reasoner.py` |
| SemanticFactEnricher | ✅ `semantic_fact_enricher.py` |
| Feature flags gating ontology | ✅ `feature_flags.py` |
| INF_NS = `http://inferra.ai/schema#` | ✅ |
| FUSEKI_URL env var | ✅ `fuseki_adapter.py:33` |
| SPARQL property path `rdfs:subClassOf*` | ✅ (Jena supports this) |
| Ontology chat API exists | ✅ `/api/v1/ontology/chat/query` |
| PROV-O provenance | ✅ `prov_o_trace_generator.py` |

### ❌ GUIDE Claims — Non-Existent Code (22 references)

| What GUIDE References | Actual Codebase |
|----------------------|-----------------|
| `SNOMEDAdapter` class | ❌ Not in `src/` — exists only in GUIDE text |
| `MBSAdapter` class | ❌ Not in `src/` — exists only in GUIDE text |
| `SnomedMbsOntologyService` class | ❌ Not in `src/` — exists only in GUIDE text |
| `src/adapters/outbound/ontology/snomed_adapter.py` | ❌ File does not exist |
| `src/adapters/outbound/ontology/mbs_adapter.py` | ❌ File does not exist |
| `src/services/snomed_mbs_ontology_service.py` | ❌ File does not exist |
| `src/adapters/inbound/http/routes/clinical.py` | ❌ Route file does not exist |
| `/api/v1/clinical/mbs/{item}/eligibility` | ❌ No such endpoint |
| `/api/v1/clinical/snomed/lookup` | ❌ No such endpoint |
| `/api/v1/clinical/snomed/is-descendant` | ❌ No such endpoint |
| `FUSEKI_SNOMED_DATASET` env var | ❌ Not in `config.py` — only `FUSEKI_URL` |
| `FUSEKI_MBS_DATASET` env var | ❌ Not in `config.py` |
| `FUSEKI_CROSSWALK_DATASET` env var | ❌ Not in `config.py` |
| `INFERRA_ASYNC_POST_REASONING` env var | ❌ Not in `feature_flags.py` — only `ASYNC_SYNC_ENABLED` |
| `snomed_ancestry` PostgreSQL table | ❌ No migration/schema for this |
| MBS RDF schema (`.ttl` files) | ❌ No Turtle files in repo |
| SNOMED↔MBS crosswalk graph data | ❌ No data or loader |
| `FusekiAdapter.execute_query()` method | ❌ Actual method is `execute_guarded_select()` (read) and `execute_sparql_idempotent_insert()` (write) |
| `FusekiAdapter.execute_ask()` method | ❌ Not in `FusekiAdapter` — ASK queries would use `execute_guarded_select()` and check `boolean` in response |

### ⚠️ GUIDE Claims — Partially Inaccurate

| GUIDE Claim | Issue |
|-------------|-------|
| MBS schema uses `owl:Class`, `owl:DatatypeProperty`, `owl:ObjectProperty` | Should use `rdfs:Class`, `rdf:Property` — INFERRA is RDF-based, OWL predicates are data not semantics |
| Architecture diagram says "Fuseki + OWL" | Should say "Fuseki + RDF" (fixed in prev enhancement but verify) |
| `find_mbs_items_for_diagnosis()` uses `owl:unionOf/rdf:rest*/rdf:first` | Complex OWL list traversal — simpler to use flat `mbs:allowsDiagnosis` triples |
| `MBSAdapter.__init__` takes `fuseki_adapter: FusekiAdapter` | `FusekiAdapter` is static-method-oriented; direct HTTP is simpler |
| MBS `check_eligibility()` doesn't call `is_descendant_of()` | Eligibility logic is stub-only, missing the SNOMED hierarchy check |

---

## 3. THREE-WAY GAP MATRIX — PLAN ↔ GUIDE ↔ CODE

### Knowledge Gaps: PLAN Has, GUIDE Missing

| Knowledge Element | PLAN Status | GUIDE Status | Severity |
|------------------|------------|--------------|----------|
| **RF2→RDF ETL pipeline pseudocode** | ✅ Detailed | ❌ Missing entirely | 🔴 HIGH |
| **MBS-SNOMED Map Refset (`der2_cRefset_MBSMapFull`)** | ✅ Explained | ❌ Not mentioned | 🔴 HIGH |
| **OntologyBindingResolver (exact label matching)** | ✅ Referenced | ❌ Not mentioned | 🟡 MEDIUM |
| **SNOMED attribute traversal limitation** | ✅ Explicitly called out | ❌ Not mentioned | 🟡 MEDIUM |
| **Fuzzy label matching gap** | ✅ Noted | ❌ Not mentioned | 🟡 MEDIUM |
| **NCTS API gap** | ✅ Noted | ❌ Not mentioned | 🟡 MEDIUM |
| **OntologyIndex in-memory scale warning** | ✅ Warned | ❌ Not mentioned | 🟡 MEDIUM |
| **ECL (Expression Constraint Language) gap** | ✅ Noted | ❌ Not mentioned | 🟢 LOW |
| **SNOMED concrete domains gap** | ✅ Noted | ❌ Not mentioned | 🟢 LOW |
| **Incremental RF2 delta loading gap** | ✅ Noted | ❌ Not mentioned | 🟢 LOW |
| **3-tier implementation approach** | ✅ Structured | ⚠️ Has 5 flat phases | 🟡 MEDIUM |

### Implementation Gaps: GUIDE Has, PLAN Missing

| Implementation Element | GUIDE Status | PLAN Status | Severity |
|----------------------|-------------|-------------|----------|
| **SNOMEDAdapter class (copy-paste)** | ✅ Provided | ❌ Not included | 🟢 LOW |
| **MBSAdapter class (copy-paste)** | ✅ Provided | ❌ Not included | 🟢 LOW |
| **SnomedMbsOntologyService** | ✅ Provided | ❌ Not included | 🟢 LOW |
| **clinical.py route scaffolding** | ✅ Provided | ❌ Not included | 🟢 LOW |
| **MBS RDF schema (Turtle)** | ✅ Provided | ❌ Briefly mentioned | 🟢 LOW |
| **INFERRA rule examples (billing)** | ✅ Provided | ❌ Briefly mentioned | 🟢 LOW |
| **HTTP API usage examples (curl)** | ✅ Provided | ❌ Not included | 🟢 LOW |
| **End-to-end validation test** | ✅ Provided | ❌ Not included | 🟡 MEDIUM |
| **Error handling patterns** | ✅ Provided | ❌ Not included | 🟢 LOW |
| **Performance considerations** | ✅ Provided | ⚠️ Briefly in PLAN | 🟢 LOW |

### Both Documents: Different Strengths

| Strength | PLAN | GUIDE |
|----------|------|-------|
| Accuracy vs codebase | ✅ High | ⚠️ 22 non-existent references |
| Architecture integrity | ✅ Clean, verified | ⚠️ Proposes adapters not in platform |
| Workarounds for gaps | ✅ 6+ workarounds | ❌ Only config reality check |
| Developer execution path | ❌ No code samples | ✅ Full adapters, routes, tests |
| Business/regulatory context | ⚠️ Brief | ✅ Australian use cases + licensing |
| Readability for devs | ✅ Tables + ASCII art | ⚠️ Verbose, some redundancy |

---

## 4. Concrete Gaps — What Must Change in the GUIDE

### 🔴 Critical Gap 1: Missing RF2→RDF ETL Pipeline

**What PLAN has that GUIDE doesn't:**

```python
# From PLAN Section 5, Step 1 — never appears in GUIDE
# SNOMED-CT AU RF2 release files → RDF conversion

for row in read_rf2("sct2_Concept_Full_AU1000036.txt"):
    graph.add((URIRef(f"http://snomed.info/id/{row.conceptId}"), RDF.type, OWL.Class))

for row in read_rf2("sct2_Description_Full_AU1000036.txt"):
    if row.active and row.typeId == "900000000000013009":
        graph.add((URIRef(f"http://snomed.info/id/{row.conceptId}"), RDFS.label, Literal(row.term, lang="en-AU")))

for row in read_rf2("sct2_Relationship_Full_AU1000036.txt"):
    if row.active and row.typeId == "116680003":  # IS-A
        graph.add((URIRef(f"http://snomed.info/id/{row.sourceId}"), RDFS.subClassOf, URIRef(f"http://snomed.info/id/{row.destinationId}")))
```

**Why it matters:** The GUIDE assumes RDF already exists. In practice, SNOMED-CT AU comes as RF2 tab-delimited files — you MUST convert. This is the #1 practical blocker.

### 🔴 Critical Gap 2: Missing MBS Map Refset

**What PLAN has that GUIDE doesn't:**

```python
# From PLAN Section 5, Step 3 — the MBS↔SNOMED bridge
for row in read_rf2("der2_cRefset_MBSMapFull_AU1000036.txt"):
    if row.active:
        graph.add((
            URIRef(f"http://inferra.ai/mbs/{row.mapTarget}"),
            OWL.equivalentClass,
            URIRef(f"http://snomed.info/id/{row.referencedComponentId}"),
        ))
```

**Why it matters:** The GUIDE's "crosswalk" is manually authored. The real bridge exists in the SNOMED-CT AU release itself as a refset file. This file is the authoritative MBS↔SNOMED mapping.

### 🟡 Medium Gap 3: OntologyBindingResolver Not Mentioned

The GUIDE proposes `SNOMEDAdapter.lookup_concept()` for label-based lookups, but the platform already has `OntologyBindingResolver` that does **exact casefold label matching** between rule fact names and ontology IRIs. The GUIDE should use this existing machinery instead of reimplementing label matching in adapters.

### 🟡 Medium Gap 4: SNOMED Attribute Traversal Limitation

PLAN explicitly states:
> "SemanticFactEnricher only derives tags for the built-in set (rdfs:domain, rdfs:range, rdfs:subPropertyOf, rdf:type, owl:equivalentClass). Custom attribute traversal would require extending the enricher or using the SPARQL chat endpoint."

GUIDE never mentions that SNOMED attribute relationships (HAS_FINDING_SITE, HAS_PROCEDURE_MORPHOLOGY, etc.) won't be enriched by the platform — only IS-A and equivalentClass closures work automatically.

### 🟡 Medium Gap 5: OntologyIndex In-Memory Scale Warning

PLAN warns:
> "In-memory OntologyIndex loads all triples. For full SNOMED (~400K concepts, ~1.5M relationships), use SPARQL/Fuseki path; load only relevant subsets into OntologyIndex."

GUIDE never addresses the 400K-concept scale limit of `OntologyIndex`. The proposed adapters via SPARQL are the right approach, but GUIDE should explicitly note that `OntologyIndex` is for subsets, not full SNOMED.

### 🟢 Low Gap 6: Fuzzy Label Matching

PLAN notes exact match only. GUIDE proposes `lookup_concept()` by exact SCTID. Neither covers the real-world problem: a rule fact named `has_myocardial_infarction` won't match `"Myocardial infarction (disorder)"` exactly. Pre-normalization of SNOMED labels is required.

### 🟢 Low Gap 7: NCTS API, ECL, Concrete Domains

PLAN lists these as ❌ not supported. GUIDE should at minimum mention these as future roadmap items.

---

## 5. Enhancement Plan for SNOMED_MBS_INTEGRATION_GUIDE.md

### Phase A: Add PLAN's Knowledge (resolve 🔴 Critical gaps)

#### A1. Add "Part 0: Loading SNOMED-CT AU — RF2 to RDF Conversion"

Move from "download SNOMED OWL file" (wrong — SNOMED ships RF2, not OWL) to actual RF2→RDF conversion. Insert after current Step 1.

**Content to add:**
- RF2 file structure explanation (Concept, Description, Relationship, Refset files)
- Python pseudocode for each file type
- Active/inactive concept filtering (only load `active=1`)
- Language refset filtering (en-AU preferred terms)
- Expected output size: ~1.2-1.5M triples for full SNOMED
- Fuseki loading command with named graph

#### A2. Add "The MBS-SNOMED Map Refset" section

Insert after MBS RDF schema. Explain that the authoritative mapping already exists in the SNOMED-CT AU release as `der2_cRefset_MBSMapFull_AU1000036.txt`.

**Content to add:**
- Refset file structure (referencedComponentId = SNOMED concept, mapTarget = MBS item number)
- Conversion pseudocode
- Why this is better than manual crosswalks
- Loading as a third named graph

#### A3. Add "Honest Assessment: What Works, What Needs Work" as a named section

Currently scattered across Quick Reference and Part 6. Consolidate into a single ✅/⚠️/❌ table similar to PLAN's format.

### Phase B: Fix Code Gaps (resolve ❌ non-existent code references)

#### B1. Replace all adapter code with PLAN-aligned approach

Instead of proposing new `SNOMEDAdapter`/`MBSAdapter` classes, demonstrate how to use the **existing** platform components:

- `OntologyBindingResolver` for label→IRI matching (instead of custom lookup)
- `OntologyIndex.class_ancestors()` for hierarchy traversal (instead of custom SPARQL)
- `FusekiAdapter.execute_guarded_select()` for ad-hoc queries (instead of custom `_execute_query`)
- `OntologyReasoner.materialize()` for INFERRED layer derivation

#### B2. Add "Using Existing Platform Components for SNOMED" section

Show how the platform's machinery already handles SNOMED without custom adapters:

```python
# Load SNOMED into Fuseki named graph
# OntologyBindingResolver auto-matches rule facts to SNOMED labels
# OntologyReasoner auto-derives subclass facts
# No custom adapter needed for basic hierarchy reasoning
```

### Phase C: Fill Knowledge Gaps (resolve 🟡 Medium gaps)

#### C1. Add "Limitations of Current Ontology Support" table

| Limitation | Impact | Workaround |
|-----------|--------|------------|
| SNOMED attribute traversal not enriched | HAS_FINDING_SITE etc. not auto-derived | Use SPARQL chat endpoint |
| Exact label matching only | `has_mi` won't match `"Myocardial infarction"` | Pre-normalize SNOMED labels |
| OntologyIndex in-memory scale | Full SNOMED won't fit | Use Fuseki SPARQL; load subsets |
| No NCTS API adapter | No real-time terminology lookup | Batch load quarterly releases |
| No ECL parser | No SNOMED expression queries | Use SPARQL or natural language chat |

#### C2. Replace 5-phase roadmap with PLAN's 3-tier approach

- Tier 1 (Week 1-2): Subset loading for relevant clinical domain
- Tier 2 (Week 3-4): Rule integration + ontology profile usage
- Tier 3 (Month 2+): Full SNOMED + extended enrichers + fuzzy matching

---

## 6. Recommended Final GUIDE Structure

```
# SNOMED-CT AU & MBS Integration Guide for INFERRA Platform

## Quick Reference: INFERRA Ontology Capabilities
## What Exists Today vs What You Must Build

## Part 0: Understanding the Data Sources
    ### SNOMED-CT AU RF2 Format (not OWL!)
    ### MBS as a Regulatory Code Set
    ### The MBS-SNOMED Map Refset (der2_cRefset_MBSMapFull)

## Part 1: Loading Data — RF2 to RDF Conversion
    ### Step 1: Convert SNOMED RF2 → RDF
    ### Step 2: Convert MBS → RDF
    ### Step 3: Convert MBS Map Refset → RDF
    ### Step 4: Load into Fuseki Named Graphs

## Part 2: Using Existing Platform Ontology Machinery
    ### OntologyBindingResolver: Label → IRI Matching
    ### OntologyIndex: Hierarchy Traversal
    ### OntologyReasoner: Materialized Inference
    ### Ontology Chat: Natural Language SPARQL
    ### Decision Path: Ontology-Backed Traceability

## Part 3: Writing Clinical Rules with SNOMED/MBS
    ### Rule Set Examples (billing, CDM, MHCP)
    ### ontology_profile: full_semantic_pilot
    ### Feeding SCTID Values into Sessions

## Part 4: Honest Assessment
    ### ✅ Works Today (no code changes)
    ### ⚠️ Requires Workarounds
    ### ❌ Not Supported (needs new code)
    ### Performance & Scale Limits

## Part 5: Implementation Roadmap (3-Tier)
    ### Tier 1: Subset Loading (Week 1-2)
    ### Tier 2: Rule Integration (Week 3-4)
    ### Tier 3: Full Production (Month 2+)

## Part 6: End-to-End Validation Test

## Part 7: Australian Healthcare Use Cases
```

---

## 7. Summary of Required Changes

| Priority | Change | Lines Affected | Effort |
|----------|--------|---------------|--------|
| 🔴 P0 | Add RF2→RDF ETL pipeline section | ~80 new lines | Medium |
| 🔴 P0 | Add MBS Map Refset section | ~40 new lines | Small |
| 🔴 P0 | Add "Understanding RF2 Format" intro | ~50 new lines | Small |
| 🟡 P1 | Replace custom adapters with platform component usage | ~200 lines (restructure Part 3, Step 5-6) | Large |
| 🟡 P1 | Add "Limitations" table (SNOMED attributes, fuzzy match, scale) | ~30 new lines | Small |
| 🟡 P1 | Consolidate "Honest Assessment" into single section | ~20 lines (reorganize) | Small |
| 🟡 P1 | Replace 5-phase with 3-tier roadmap | ~30 lines (rewrite Part 5) | Small |
| 🟢 P2 | Remove non-existent env vars (already done) | Already fixed | Done |
| 🟢 P2 | Fix MBS schema owl:→rdf: (already done) | Already fixed | Done |
| 🟢 P2 | Remove duplicate sections | ~50 lines removed | Small |

**Total estimated change:** ~600 lines rewritten, ~150 lines added, ~50 lines removed
**Net file size:** ~1,900 lines (~68KB) — reasonable for a comprehensive guide

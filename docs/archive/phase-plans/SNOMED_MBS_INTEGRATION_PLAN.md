 ────────────────────────────────────────────────────────────────────────────────

 SNOMED-CT AU and MBS — What They Are, and Integration via the inferra-platform Ontology

 ────────────────────────────────────────────────────────────────────────────────

 > **Archived:** 2026-07-16. This plan is superseded by
 > `docs/SNOMED CT AU and MBS related/SNOMED_MBS_INTEGRATION_GUIDE.md`.

 ### 1. What is SNOMED-CT AU?

 SNOMED-CT (Systematized Nomenclature of Medicine — Clinical Terms) is the global standard clinical healthcare
 terminology. It is a concept-based, formally defined, multilingual vocabulary covering:

 - Diseases / diagnoses (e.g., Type 2 diabetes mellitus)
 - Procedures (e.g., Excision of lesion of skin)
 - Body structures (e.g., Structure of left kidney)
 - Observable entities / findings (e.g., Blood glucose level)
 - Substances / medications (e.g., Metformin 500mg tablet)
 - Situations / contexts (e.g., Procedure on outpatient basis)

 Concepts are organized in a directed acyclic graph (DAG) linked by relationships:
 - IS-A (subtype / subClassOf) — Type 2 diabetes mellitus IS-A Diabetes mellitus
 - Attribute relationships — HAS_FINDING_SITE, HAS_PROCEDURE_SITE, HAS_METHOD, etc.

 SNOMED-CT AU is the Australian national extension, distributed by the National Clinical Terminology Service (NCTS)
 (https://www.digitalhealth.gov.au/initiatives-and-programs/national-clinical-terminology-service). It adds:
 - Australian-specific concept extensions
 - Medication concepts linked to PBS (Pharmaceutical Benefits Scheme)
 - MBS mapping reference sets — the bridge to the Medicare Benefits Schedule

 SNOMED-CT AU is distributed as RF2 release files — tab-delimited flat files containing:
 - Concept file (concept ID, status, definition status)
 - Description file (synonyms, preferred terms in en-AU)
 - Relationship file (IS-A, attribute relationships)
 - Reference Set files (subsets, language refsets, MBS map refset)

 ────────────────────────────────────────────────────────────────────────────────

 ### 2. What is MBS?

 The Medicare Benefits Schedule (MBS) is Australia's government-subsidized medical services fee schedule. Each MBS item
 number represents:

 ┌─────────────────────┬───────────────────────────────────────────┐
 │ Aspect              │ Example                                   │
 ├─────────────────────┼───────────────────────────────────────────┤
 │ Item number         │ 23                                        │
 ├─────────────────────┼───────────────────────────────────────────┤
 │ Description         │ Professional attendance by a GP — Level B │
 ├─────────────────────┼───────────────────────────────────────────┤
 │ Fee                 │ $39.75                                    │
 ├─────────────────────┼───────────────────────────────────────────┤
 │ Schedule group      │ A1 (General Practitioner)                 │
 ├─────────────────────┼───────────────────────────────────────────┤
 │ Rules               │ ≥20 min, not with items 3–27 same day     │
 ├─────────────────────┼───────────────────────────────────────────┤
 │ Patient eligibility │ Medicare-eligible                         │
 └─────────────────────┴───────────────────────────────────────────┘

 Key features:
 - ~6,000+ active item numbers
 - Hierarchical grouping (Group A1 = GP, Group A2 = Specialist, etc.)
 - Complex billing rules: time thresholds, co-claiming restrictions, patient demographics
 - Updated quarterly by Services Australia

 The MBS is NOT an ontology — it is a regulatory code set. But it has structure (groups, subgroups, items) and rules
 that can be formalized.

 ────────────────────────────────────────────────────────────────────────────────

 ### 3. How They Connect: The MBS–SNOMED Map

 The SNOMED-CT AU release includes a MBS Reference Set (Refset) that maps MBS item numbers to SNOMED-CT procedure
 concepts:

 ```
   MBS Item 23  ←→  SNOMED-CT 183509004 "General practitioner consultation"
   MBS Item 36  ←→  SNOMED-CT 183510009 "Extended general practitioner consultation"
 ```

 This is the bridge — it lets you reason from clinical concepts to billing codes and vice versa.

 ────────────────────────────────────────────────────────────────────────────────

 ### 4. Can the inferra-platform Integrate Them Via Ontology?

 Yes — with important caveats. Let me map exactly what the platform's ontology subsystem supports vs. what SNOMED-CT AU
 / MBS require.

 #### 4.1 What the Platform Already Supports

 The platform has a mature RDF/OWL-aligned ontology stack:

 ┌─────────────────────────┬────────────────────────────────────────────┬─────────────────────────────────────────────┐
 │ Capability              │ Component                                  │ Status                                      │
 ├─────────────────────────┼────────────────────────────────────────────┼─────────────────────────────────────────────┤
 │ RDF triple storage      │ FusekiAdapter → Apache Fuseki              │ ✅ Production                               │
 ├─────────────────────────┼────────────────────────────────────────────┼─────────────────────────────────────────────┤
 │ SPARQL query            │ execute_guarded_select() with safety       │ ✅ Production                               │
 │                         │ validation                                 │                                             │
 ├─────────────────────────┼────────────────────────────────────────────┼─────────────────────────────────────────────┤
 │ Idempotent SPARQL       │ execute_sparql_idempotent_insert()         │ ✅ Production                               │
 │ INSERT                  │                                            │                                             │
 ├─────────────────────────┼────────────────────────────────────────────┼─────────────────────────────────────────────┤
 │ Named graph management  │ list_named_graphs(),                       │ ✅ Production                               │
 │                         │ get_named_graph_triples()                  │                                             │
 ├─────────────────────────┼────────────────────────────────────────────┼─────────────────────────────────────────────┤
 │ Ontology chat (NL →     │ /api/v1/ontology/chat/query                │ ✅ Production                               │
 │ SPARQL)                 │                                            │                                             │
 ├─────────────────────────┼────────────────────────────────────────────┼─────────────────────────────────────────────┤
 │ Decision-path reasoning │ /api/v1/ontology/decision-path             │ ✅ Production                               │
 ├─────────────────────────┼────────────────────────────────────────────┼─────────────────────────────────────────────┤
 │ RDFS subClassOf closure │ OntologyIndex.class_ancestors() BFS        │ ✅ Production                               │
 ├─────────────────────────┼────────────────────────────────────────────┼─────────────────────────────────────────────┤
 │ OWL equivalentClass     │ OntologyIndex.get_equivalent_classes()     │ ✅ Production                               │
 │                         │ bidirectional                              │                                             │
 ├─────────────────────────┼────────────────────────────────────────────┼─────────────────────────────────────────────┤
 │ rdfs:domain /           │ SemanticFactEnricher tag derivation        │ ✅ Production                               │
 │ rdfs:range              │                                            │                                             │
 ├─────────────────────────┼────────────────────────────────────────────┼─────────────────────────────────────────────┤
 │ rdfs:subPropertyOf      │ property_lineage() closure                 │ ✅ Production                               │
 ├─────────────────────────┼────────────────────────────────────────────┼─────────────────────────────────────────────┤
 │ Label-based fact        │ OntologyBindingResolver exact-label match  │ ✅ Production                               │
 │ binding                 │                                            │                                             │
 ├─────────────────────────┼────────────────────────────────────────────┼─────────────────────────────────────────────┤
 │ Semantic fact           │ SemanticFactEnricher → FactSource.SEMANTIC │ ✅ Production                               │
 │ enrichment              │  layer                                     │                                             │
 ├─────────────────────────┼────────────────────────────────────────────┼─────────────────────────────────────────────┤
 │ Ontology-derived        │ OntologyReasoner.materialize() →           │ 🔒 Feature-flagged                          │
 │ inference               │ FactSource.INFERRED                        │ (ONTOLOGY_REASONING_ENABLED)                │
 ├─────────────────────────┼────────────────────────────────────────────┼─────────────────────────────────────────────┤
 │ Auto-answer from        │ OntologyValueSuggestion                    │ 🔒 Feature-flagged                          │
 │ ontology                │                                            │ (ONTOLOGY_AUTO_ANSWER_ENABLED)              │
 ├─────────────────────────┼────────────────────────────────────────────┼─────────────────────────────────────────────┤
 │ Advisory suggestions    │ SemanticSuggestion                         │ 🔒 Feature-flagged                          │
 │                         │                                            │ (ONTOLOGY_ADVISORY_ENABLED)                 │
 ├─────────────────────────┼────────────────────────────────────────────┼─────────────────────────────────────────────┤
 │ Question strategy       │ SemanticQuestionStrategy                   │ 🔒 Feature-flagged                          │
 │                         │                                            │ (ONTOLOGY_QUESTION_STRATEGY_ENABLED)        │
 ├─────────────────────────┼────────────────────────────────────────────┼─────────────────────────────────────────────┤
 │ PROV-O trace generation │ ProvOTraceGenerator                        │ 🔒 Feature-flagged (PROV_O_TRACE)           │
 └─────────────────────────┴────────────────────────────────────────────┴─────────────────────────────────────────────┘

 The supported RDF/RDFS/OWL subset is:
 - rdf:type (instance classification)
 - rdfs:subClassOf (class hierarchy)
 - rdfs:subPropertyOf (property hierarchy)
 - rdfs:domain / rdfs:range (property constraints)
 - rdfs:label (human-readable labels)
 - owl:equivalentClass (class equivalence)
 - inf:name, inf:hasItem, inf:valueType, inf:defaultValue, inf:confidence, inf:minimum, inf:maximum (INFERRA-specific
 properties)

 #### 4.2 What SNOMED-CT AU Needs

 SNOMED-CT's relational structure maps well to the platform's supported subset:

 ┌───────────────────────────────────────────────┬───────────────────────────────────┬────────────────────────────────┐
 │ SNOMED-CT Concept                             │ RDF Representation                │ Platform Support               │
 ├───────────────────────────────────────────────┼───────────────────────────────────┼────────────────────────────────┤
 │ IS-A relationship                             │ rdfs:subClassOf                   │ ✅ Fully supported             │
 ├───────────────────────────────────────────────┼───────────────────────────────────┼────────────────────────────────┤
 │ Concept descriptions/synonyms                 │ rdfs:label                        │ ✅ Fully supported             │
 ├───────────────────────────────────────────────┼───────────────────────────────────┼────────────────────────────────┤
 │ Concept active status                         │ inf:confidence / custom predicate │ ⚠️ Workaround needed           │
 ├───────────────────────────────────────────────┼───────────────────────────────────┼────────────────────────────────┤
 │ Attribute relationships (HAS_FINDING_SITE,    │ rdfs:subPropertyOf hierarchy      │ ✅ Supported as custom         │
 │ etc.)                                         │                                   │ properties                     │
 ├───────────────────────────────────────────────┼───────────────────────────────────┼────────────────────────────────┤
 │ OWL equivalent classes                        │ owl:equivalentClass               │ ✅ Fully supported             │
 ├───────────────────────────────────────────────┼───────────────────────────────────┼────────────────────────────────┤
 │ Reference sets (MBS map)                      │ Named graphs with reified         │ ✅ Fuseki named graphs         │
 │                                               │ membership                        │                                │
 ├───────────────────────────────────────────────┼───────────────────────────────────┼────────────────────────────────┤
 │ SNOMED-CT module/versioning                   │ Named graph per release           │ ✅ Graph-level isolation       │
 └───────────────────────────────────────────────┴───────────────────────────────────┴────────────────────────────────┘

 Key gap: SNOMED-CT uses many specific relationship types (40+ attribute types like HAS_FINDING_SITE,
 HAS_PROCEDURE_MORPHOLOGY, DIRECT_SUBSTANCE, etc.). The platform supports these as custom predicates in RDF triples —
 they can be stored, queried via SPARQL, and used in the ontology chat. However, the SemanticFactEnricher only derives
 tags for the built-in set (rdfs:domain, rdfs:range, rdfs:subPropertyOf, rdf:type, owl:equivalentClass). Custom
 attribute traversal would require extending the enricher or using the SPARQL chat endpoint.

 #### 4.3 What MBS Needs

 MBS is simpler — it's essentially:

 ┌──────────────────────────┬──────────────────────────────────────┬────────────────────────────────────┐
 │ MBS Element              │ RDF Representation                   │ Platform Support                   │
 ├──────────────────────────┼──────────────────────────────────────┼────────────────────────────────────┤
 │ Item number              │ rdfs:label / URI slug                │ ✅                                 │
 ├──────────────────────────┼──────────────────────────────────────┼────────────────────────────────────┤
 │ Item description         │ rdfs:label / inf:name                │ ✅                                 │
 ├──────────────────────────┼──────────────────────────────────────┼────────────────────────────────────┤
 │ Schedule group hierarchy │ rdfs:subClassOf                      │ ✅                                 │
 ├──────────────────────────┼──────────────────────────────────────┼────────────────────────────────────┤
 │ Fee amount               │ inf:defaultValue or custom predicate │ ✅                                 │
 ├──────────────────────────┼──────────────────────────────────────┼────────────────────────────────────┤
 │ Billing rules            │ INFERRA rule text (native)           │ ✅ This is the platform's strength │
 ├──────────────────────────┼──────────────────────────────────────┼────────────────────────────────────┤
 │ MBS↔SNOMED map           │ Named graph with mapping triples     │ ✅ Fuseki named graphs             │
 └──────────────────────────┴──────────────────────────────────────┴────────────────────────────────────┘

 ────────────────────────────────────────────────────────────────────────────────

 ### 5. Integration Architecture

 Here is the concrete integration path:

 ```
   ┌───────────────────────────────────────────────────────────┐
   │                    INFERRA PLATFORM                       │
   │                                                           │
   │  ┌─────────────────┐     ┌───────────────────────┐        │
   │  │  INFERRA Rules  │     │  Fuseki Named Graphs  │        │
   │  │  (billing logic)│     │                       │        │
   │  │                 │     │  graph:snomed-ct-au   │        │
   │  │  TYPE daily     │     │  → IS-A hierarchy     │        │
   │  │    billing rec  │     │  → Attribute triples  │        │
   │  │    FIELD cpt    │     │  → Labels (en-AU)     │        │
   │  │     code cat    │     │                       │        │
   │  │     AS TEXT     │     │  graph:mbs-items      │        │
   │  │    FIELD mbs    │     │  → Item hierarchy     │        │
   │  │     item AS TEXT│     │  → Fee triples        │        │
   │  │    FIELD mbs    │     │  → Rule annotations   │        │
   │  │     fee AS      │     │                       │        │
   │  │     NUMBER      │     │  graph:mbs-snomed-map │        │
   │  │                 │     │  → MBS item ↔ SNOMED  │        │
   │  │  INPUT ledger   │     │    concept triples    │        │
   │  │    AS COLLECTION│     │                       │        │
   │  │    OF daily     │     └───────────┬───────────┘        │
   │  │    billing rec  │                 │                    │
   │  │                 │                 │ SPARQL /           │
   │  │  SOME item IN   │◀───────────────┘ OntologyIndex      │
   │  │    ledger       │                                      │
   │  │    AND item.    │     ┌────────────────────────┐       │
   │  │    cpt code     │     │  OntologyReasoner      │       │
   │  │    category     │     │  (materialize into     │       │
   │  │    IS IN LIST:  │     │   INFERRED layer)      │       │
   │  │    global       │     │                        │       │
   │  │    package      │     │  SemanticFactEnricher  │       │
   │  │    component    │     │  (tag into SEMANTIC    │       │
   │  │    codes        │     │   layer)               │       │
   │  └─────────────────┘     └────────────────────────┘       │
   │                                                           │
   │  Ontology Chat: "Which MBS items cover GP consultations   │
   │  for patients with Type 2 diabetes?"                      │
   │  → SPARQL over snomed-ct-au + mbs-snomed-map graphs       │
   └───────────────────────────────────────────────────────────┘
 ```

 #### Step-by-Step Integration Plan

 Step 1: Convert SNOMED-CT AU RF2 → RDF/Turtle

 Write a one-time ETL pipeline that reads RF2 files and produces RDF triples:

 ```python
   # Pseudocode for RF2 → RDF converter
   # Input: SNOMED-CT AU RF2 release files
   # Output: Turtle (.ttl) file loadable into Fuseki

   # Concepts → owl:Class with rdfs:label
   for row in read_rf2("sct2_Concept_Full_AU1000036.txt"):
       graph.add((
           URIRef(f"http://snomed.info/id/{row.conceptId}"),
           RDF.type, OWL.Class,
       ))

   # Descriptions → rdfs:label (en-AU preferred)
   for row in read_rf2("sct2_Description_Full_AU1000036.txt"):
       if row.active and row.typeId == "900000000000013009":  # synonym
           graph.add((
               URIRef(f"http://snomed.info/id/{row.conceptId}"),
               RDFS.label, Literal(row.term, lang="en-AU"),
           ))

   # IS-A relationships → rdfs:subClassOf
   for row in read_rf2("sct2_Relationship_Full_AU1000036.txt"):
       if row.active and row.typeId == "116680003":  # IS-A
           graph.add((
               URIRef(f"http://snomed.info/id/{row.sourceId}"),
               RDFS.subClassOf,
               URIRef(f"http://snomed.info/id/{row.destinationId}"),
           ))

   # Attribute relationships → custom predicates
   for row in read_rf2("sct2_Relationship_Full_AU1000036.txt"):
       if row.active and row.typeId != "116680003":
           graph.add((
               URIRef(f"http://snomed.info/id/{row.sourceId}"),
               URIRef(f"http://snomed.info/id/{row.typeId}"),
               URIRef(f"http://snomed.info/id/{row.destinationId}"),
           ))
 ```

 Step 2: Convert MBS → RDF + Named Graph

 ```python
   # MBS items as RDF in a separate named graph
   for item in parse_mbs_xml():
       item_uri = URIRef(f"http://inferra.ai/mbs/{item.number}")
       graph.add((item_uri, RDFS.label, Literal(item.description)))
       graph.add((item_uri, RDFS.subClassOf, URIRef(f"http://inferra.ai/mbs/Group/{item.group}")))
       graph.add((item_uri, INF_NS.defaultValue, Literal(item.fee)))
 ```

 Step 3: Load MBS–SNOMED Map Refset → RDF

 ```python
   # The MBS refset from the SNOMED-CT AU release
   for row in read_rf2("der2_cRefset_MBSMapFull_AU1000036.txt"):
       if row.active:
           graph.add((
               URIRef(f"http://inferra.ai/mbs/{row.mapTarget}"),  # MBS item number
               OWL.equivalentClass,
               URIRef(f"http://snomed.info/id/{row.referencedComponentId}"),  # SNOMED concept
           ))
 ```

 Step 4: Load into Fuseki Named Graphs

 ```bash
   # Three separate named graphs
   ./s-put http://localhost:3030/inferra/data?graph=http://snomed.info/au snomed-au.ttl
   ./s-put http://localhost:3030/inferra/data?graph=http://inferra.ai/mbs mbs.ttl
   ./s-put http://localhost:3030/inferra/data?graph=http://inferra.ai/mbs-snomed-map mbs-snomed-map.ttl
 ```

 Step 5: Use in INFERRA Rules

 Once loaded, the ontology binding system will automatically match rule fact names to SNOMED labels:

 ```python
   RULE SET: Australian Billing Compliance

   IMPORT: global package component codes

   TYPE daily billing record
       FIELD cpt code category AS TEXT
       FIELD mbs item AS TEXT
       FIELD mbs fee AS NUMBER

   INPUT daily billing ledger AS COLLECTION OF daily billing record

   SOME item IN daily billing ledger
       AND item.cpt code category IS IN LIST: global package component codes
 ```

 When a session runs with an ontology profile that includes the SNOMED graph:

 1. OntologyBindingResolver matches "cpt code category" → SNOMED concept IRI via rdfs:label
 2. SemanticFactEnricher adds SEMANTIC-layer tags (subclass ancestry, type classification)
 3. OntologyReasoner.materialize() derives INFERRED facts from the IS-A closure
 4. The ontology chat endpoint allows natural-language queries like "Which SNOMED concepts map to MBS item 23?"

 Step 6: Enable Feature Flags

 ```bash
   # Required for ontology-driven reasoning
   export INFERRA_ONTOLOGY_ADVISORY_ENABLED=true
   export INFERRA_ONTOLOGY_AUTO_ANSWER_ENABLED=true
   export INFERRA_ONTOLOGY_REASONING_ENABLED=true
   export INFERRA_ONTOLOGY_QUESTION_STRATEGY_ENABLED=true

   # Or use the "full_semantic_pilot" profile per-session:
   # POST /api/v1/sessions  { "ontology_profile": "full_semantic_pilot" }
 ```

 ────────────────────────────────────────────────────────────────────────────────

 ### 6. Honest Assessment — What Works, What Doesn't

 #### ✅ Works Today (No Code Changes)

 ┌──────────────────────────────────────────────┬───────────────────────────────────────────┐
 │ Capability                                   │ How                                       │
 ├──────────────────────────────────────────────┼───────────────────────────────────────────┤
 │ Store SNOMED-CT AU as RDF triples in Fuseki  │ Named graph http://snomed.info/au         │
 ├──────────────────────────────────────────────┼───────────────────────────────────────────┤
 │ Query SNOMED hierarchy via SPARQL            │ /api/v1/ontology/chat/query               │
 ├──────────────────────────────────────────────┼───────────────────────────────────────────┤
 │ IS-A traversal (subClassOf closure)          │ OntologyIndex.class_ancestors()           │
 ├──────────────────────────────────────────────┼───────────────────────────────────────────┤
 │ Equivalent class resolution                  │ OntologyIndex.get_equivalent_classes()    │
 ├──────────────────────────────────────────────┼───────────────────────────────────────────┤
 │ Bind rule facts to SNOMED concepts by label  │ OntologyBindingResolver exact-label match │
 ├──────────────────────────────────────────────┼───────────────────────────────────────────┤
 │ Semantic enrichment (SEMANTIC layer tags)    │ SemanticFactEnricher                      │
 ├──────────────────────────────────────────────┼───────────────────────────────────────────┤
 │ Ontology-derived inference (INFERRED layer)  │ OntologyReasoner.materialize()            │
 ├──────────────────────────────────────────────┼───────────────────────────────────────────┤
 │ Auto-answer from ontology defaults           │ OntologyValueSuggestion                   │
 ├──────────────────────────────────────────────┼───────────────────────────────────────────┤
 │ MBS items as separate named graph            │ Fuseki multi-graph support                │
 ├──────────────────────────────────────────────┼───────────────────────────────────────────┤
 │ MBS↔SNOMED mapping via owl:equivalentClass   │ Bidirectional closure                     │
 ├──────────────────────────────────────────────┼───────────────────────────────────────────┤
 │ PROV-O trace of ontology derivations         │ ProvOTraceGenerator                       │
 ├──────────────────────────────────────────────┼───────────────────────────────────────────┤
 │ Rule validation against ontology constraints │ /api/v1/ontology/decision-path            │
 └──────────────────────────────────────────────┴───────────────────────────────────────────┘

 #### ⚠️ Requires Extension / Workarounds

 ┌────────────────────────────────┬────────────────────────────────────────┬──────────────────────────────────────────┐
 │ Capability                     │ Issue                                  │ Workaround                               │
 ├────────────────────────────────┼────────────────────────────────────────┼──────────────────────────────────────────┤
 │ SNOMED attribute traversal     │ SemanticFactEnricher only derives tags │ Use SPARQL chat for ad-hoc queries;      │
 │ (HAS_FINDING_SITE, etc.)       │ for built-in predicates                │ extend enricher for custom predicates    │
 ├────────────────────────────────┼────────────────────────────────────────┼──────────────────────────────────────────┤
 │ Fuzzy label matching           │ OntologyBindingResolver uses exact     │ Pre-normalize SNOMED preferred terms to  │
 │                                │ casefold match                         │ match rule variable names, or add a      │
 │                                │                                        │ fuzzy matcher                            │
 ├────────────────────────────────┼────────────────────────────────────────┼──────────────────────────────────────────┤
 │ SNOMED inactive concepts       │ No built-in active/inactive filtering  │ Only load active=true concepts in the    │
 │                                │ in the ontology index                  │ ETL step                                 │
 ├────────────────────────────────┼────────────────────────────────────────┼──────────────────────────────────────────┤
 │ MBS rule formalization         │ MBS billing rules are in PDF prose     │ Encode billing constraints as INFERRA    │
 │                                │                                        │ rules natively (this is the platform's   │
 │                                │                                        │ strength)                                │
 ├────────────────────────────────┼────────────────────────────────────────┼──────────────────────────────────────────┤
 │ SNOMED versioning              │ Named graphs isolate versions, but no  │ Load each quarterly release as a new     │
 │                                │ built-in RF2 version diffing           │ named graph; manage versions via graph   │
 │                                │                                        │ URIs                                     │
 ├────────────────────────────────┼────────────────────────────────────────┼──────────────────────────────────────────┤
 │ Scale (~400K SNOMED concepts,  │ In-memory OntologyIndex loads all      │ For full SNOMED, use the SPARQL/Fuseki   │
 │ ~1.5M relationships)           │ triples                                │ path; load only relevant subsets into    │
 │                                │                                        │ OntologyIndex                            │
 └────────────────────────────────┴────────────────────────────────────────┴──────────────────────────────────────────┘

 #### ❌ Not Supported (Would Require New Code)

 ┌─────────────────────────────────────────────┬──────────────────────────────────────────────────────────────────────┐
 │ Capability                                  │ Gap                                                                  │
 ├─────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────┤
 │ SNOMED Expression Constraint Language       │ The platform has no ECL parser; queries must be SPARQL or natural    │
 │                                             │ language via ontology chat                                           │
 ├─────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────┤
 │ SNOMED concrete domains (numeric values on  │ OntologyIndex does not support typed literal filtering               │
 │ attributes)                                 │                                                                      │
 ├─────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────┤
 │ Refset-specific reasoning                   │ Reference sets are stored as data but the reasoner does not treat    │
 │                                             │ them specially                                                       │
 ├─────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────┤
 │ Incremental RF2 delta loading               │ No built-in RF2→RDF streaming pipeline; requires external ETL        │
 ├─────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────┤
 │ NCTS API integration                        │ No adapter for the NCTS online terminology server                    │
 ├─────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────┤
 │ OWL 2 RL full compliance                    │ Platform implements an "OWL 2 RL-aligned subset" only (per its own   │
 │                                             │ disclaimers)                                                         │
 └─────────────────────────────────────────────┴──────────────────────────────────────────────────────────────────────┘

 ────────────────────────────────────────────────────────────────────────────────

 ### 7. Recommended Approach

 For a production integration, I recommend a three-tier approach:

 1. Tier 1 — Subset Loading (Week 1–2)
     - Identify the ~1,000–5,000 SNOMED concepts relevant to your clinical domain (e.g., general practice, oncology)
     - Convert to RDF with rdfs:subClassOf, rdfs:label, owl:equivalentClass triples
     - Load MBS items and the MBS–SNOMED map as separate named graphs
     - Use the platform's existing OntologyIndex in-memory path for sessions
 2. Tier 2 — Rule Integration (Week 3–4)
     - Encode MBS billing rules as native INFERRA rules (TYPE/FIELD/INPUT/SOME/ALL)
     - Use ontology_profile: "full_semantic_pilot" for sessions that need SNOMED enrichment
     - Use the ontology chat endpoint for ad-hoc SNOMED queries
     - Let OntologyReasoner derive INFERRED facts from SNOMED hierarchies
 3. Tier 3 — Full SNOMED (Month 2+)
     - Extend SemanticFactEnricher to traverse custom SNOMED attribute predicates
     - Add a fuzzy label matcher to OntologyBindingResolver
     - Build an RF2→RDF ETL pipeline with incremental delta loading
     - Consider an NCTS API adapter for real-time terminology lookups

 Bottom line: The inferra-platform's ontology subsystem is architecturally ready for SNOMED-CT AU and MBS integration.
 The core RDF storage (Fuseki), SPARQL querying, RDFS/OWL reasoning, semantic enrichment, and fact-binding systems all
 work today. The main work is the ETL pipeline (RF2 → RDF) and rule authoring (encoding MBS billing logic in INFERRA
 syntax) — not changes to the platform itself for the subset use case.

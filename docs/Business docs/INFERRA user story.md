# INFERRA user story
1. Storing Rule Set
- INFERRA rule set is written based on its rule syntax which is specified and defined at `C:\Users\user\.pi\projects\inferra-platform\docs\INFERRA_Rule_Syntax_Dictionary.md`

## INFERRA-AXIOM user story
1. AXIOM provides a feature of authoring rule set
2. AXIOM can generate an ontology graph for each rule set
3. AXIOM can run a case against a rule set, and the case is a part of account. <br/>
For example;
    - an account registered under Doan Kusei can have multiple cases.
    - the account can be evaluated against multiple rule sets, and each top-level evaluation creates or joins a governed case.
    - while running a case, every generated provenance product (`ASSERTED / INFERRED / LEARNED / HYPOTHETICAL / SEMANTIC`) shall be appended to the immutable audit history and versioned ontology graph of the case/account. Prior `ASSERTED` facts may be offered to a future case only after current validity, subject, scope, and source checks. Other provenance products remain discoverable for audit but must be re-derived, re-queried, or human-promoted before they can affect a future case.
    - generated provenance products are not shared between accounts because they could contaminate each account's semantic analysis, unless the accounts are explicitly correlated, such as family members, friends, or interested parties in a governed case/situation.
4. AXIOM shall not modify human approved rule set nor its ontology graph of the rule set
5. AXIOM provides a feature of querying against case(s) or account(s) ontology graph with SPARQL, and LLM shall generate its query statement based on human natural language or system itself query

## INFERRA-AEGIS user story
1. AEGIS provides a feature of authoring rule set
2. AEGIS provides a feature for authoring workflow sets
3. Each workflow node can bind one or multiple rule sets.
4. AEGIS can run a case against a workflow set, and the case is a part of account. <br/>
For example;
    - an account registered under Daio Conchen or Robot number 1 can have multiple cases.
    - each workflow can have one or more steps, and each step can bind one or more rule sets, so an account can be evaluated against multiple rule sets within one workflow.
    - an account can have one or multiple workflows.
    - each account can have governed correlations.
    - hence, while running workflow steps, every generated provenance product shall be appended to the immutable audit history and versioned ontology graph of the case/account. A future case may inspect prior non-asserted products, but it must re-derive or re-query them rather than copying them into authoritative current state.
    - generated provenance products are not shared between accounts because they could contaminate each account's semantic analysis, unless the accounts are explicitly correlated, such as family members, friends, or interested parties in a governed case/situation.
    - Cross-account provenance sharing is a massive privacy risk if done implicitly. Hence, Correlations must be explicitly modeled as Governed Edges in the graph. For example, a prov:wasDerivedFrom or inf:correlatedWith edge must be established via a specific "Relationship Declaration" workflow (e.g., a signed joint-tax return, or a legally declared power-of-attorney). The BackwardChainOrchestrator will only traverse these edges if the explicit correlation fact is ASSERTED and MANDATORY.
5. AEGIS cannot modify a human-approved rule set or its ontology graph in place. Under human/governance approval, it creates a forked version. Past cases remain linked to the precedent version (preserving historical truth), while new cases are routed to the approved new version. This is enforced by ModuleRegistry content-hash pinning.
6. AEGIS provides a feature of querying against case(s) or account(s) ontology with SPARQL, and LLM shall generate its query statement based on human natural language or system itself query

## 1. Core Data Hierarchy
*   **Tenant / Workspace:** Represents the authorization, administration, and policy boundary. It remains distinct from the entity being evaluated, even where an open-source deployment operates as a single tenant.
*   **KnowledgeSubject / Account:** Represents a distinct legal, physical, or digital entity (e.g., a human like Doan Kusei, a corporation, or an autonomous asset like Robot #1).
*   **Case Envelope:** Provides shared identity, ownership, retention, and audit references only. AXIOM and AEGIS do not share one generic product-case model.
*   **AXIOM AssessmentCase:** Represents a durable legal, eligibility, entitlement, compliance, or assessment matter and can contain multiple immutable Assessment Runs.
*   **AEGIS WorkflowCase:** Represents a durable mission, incident, action request, or governed process and can contain multiple immutable Workflow Runs, node attempts, and gate evaluations.
*   **Rule Set / Workflow:** The deterministic logic and governance policies applied to a Case.

## 2. INFERRA-AXIOM (Eligibility, Entitlements & RegTech)
*   **Authoring & Graph Generation:** AXIOM provides a UI for authoring rule sets using the strict INFERRA Rule Syntax. Upon compilation, AXIOM generates a **Symbolic Dependency Graph** for the rule set, which maps to the global Domain Ontology.
*   **Case Execution & Longitudinal Provenance:** When a Case is run against an Account, all generated provenance products (`ASSERTED`, `INFERRED`, `SEMANTIC`, `LEARNED`, `HYPOTHETICAL`) are appended to the **Account's Longitudinal Knowledge Graph** and immutable audit record. This allows future Cases for the same Account to discover prior evidence without treating historical conclusions as present truth: prior assertions are revalidated, deterministic conclusions are re-derived, and semantic conclusions are re-queried.
*   **Strict Tenant Isolation:** To prevent semantic contamination and ensure privacy compliance (GDPR/HIPAA), provenance products are strictly isolated per Account. They are never shared across Accounts unless an explicit, audited **Correlation Edge** (e.g., legal dependency, family link) is established.
*   **Immutability:** AXIOM strictly prohibits the mutation of human-approved Rule Sets or their historical graphs. Changes require the creation of a new, versioned Rule Set (e.g., v1.0 -> v1.1) to preserve the legal defensibility of past Cases.
*   **Conversational Query:** AXIOM provides a natural language interface where an LLM translates human queries into strict SPARQL queries against the Account/Case PROV-O graphs, ensuring safe, deterministic data retrieval.

## 3. INFERRA-AEGIS (Autonomous Workflows & Liability Firewall)
*   **Workflow Authoring:** AEGIS extends AXIOM by allowing the authoring of **Workflow Sets**, where each node/step in a workflow can execute one or multiple Rule Sets.
*   **Agentic & Physical Execution:** AEGIS runs Cases against Workflows for autonomous agents or physical assets (e.g., Robot #1). Provenance products (including `HYPOTHETICAL` states from simulation) are appended to the asset's Account Graph to build a longitudinal safety and operational history. Hypothetical and other non-asserted historical products remain audit evidence and cannot silently become live authority.
*   **Governed Evolution:** While AXIOM enforces strict immutability, AEGIS allows for the **governed versioning** of Rule Sets (not Workflows) under strict human-in-the-loop approval, ensuring autonomous fleets can adapt to new safety regulations while maintaining an unbroken audit trail.
*   **Correlation & Swarm Intelligence:** AEGIS Accounts (e.g., a fleet of robots) can be explicitly correlated. If governance permits, a `SEMANTIC` or `LEARNED` safety finding discovered by Robot #1 can be exposed as a provenance-linked candidate to correlated robots in the same swarm. Each receiving Case must re-query, re-derive, or obtain human promotion; it must not copy the finding into authoritative current state.

## 4. Accepted technical interpretation (2026-07-20)

*   **Graph ownership:** The global Domain Ontology and every approved Rule Graph are human-governed and immutable by case execution. Automatic execution appends instance knowledge to versioned Case Graphs and the Account's longitudinal view; it does not silently alter the global ontology.
*   **Durability:** PostgreSQL is the authoritative rule, case, fact, decision, audit, outbox, and graph-catalogue store. Fuseki is the critical, rebuildable, versioned RDF/PROV-O query projection.
*   **Versioning:** Rule, execution, and Case Graph versions are immutable. Corrections create a new version linked with `supersedes`; historical versions remain queryable while retained.
*   **Retention:** Graph/provenance retention is indefinite by default and configurable through a versioned, authorized retention policy.
*   **Provenance versus authority:** Every product, including `ASSERTED`, is recorded for audit. `FactSource` records origin and does not by itself grant decision authority.
*   **AXIOM:** Deterministic `INFERRED` facts derived from accepted inputs may participate in the same rule execution. Live ontology/semantic results never alter the authoritative AXIOM conclusion; a semantic shadow run is separate and non-authoritative.
*   **AEGIS:** A semantic query result must become a typed, provenance-complete `SEMANTIC` fact and be evaluated by approved rule bindings. Raw SPARQL never transitions a workflow. Workflow nodes support one or more immutable rule bindings, explicit aggregation, denial precedence, and fail-closed unresolved outcomes.
*   **Detailed contract:** `../INFERRA_Account_Case_Ontology_and_Provenance_Architecture.md` controls the accepted case models, graph topology, reuse rules, correlation, retention, gate composition, and release sequencing.

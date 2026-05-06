# INFERRA — IterateLine Design & Recommendations

## Quantified Collection-Based Reasoning

---

## 1. Overview

`IterateLine` is a core construct in INFERRA designed to:

> Evaluate a **set of conditions against each entity within a collection**, and derive a **single aggregated outcome**.

### Example Use Case

A `person` has multiple `children`, and:

> All children must satisfy a defined condition set (e.g., age > 18).

---

## 2. Formal Definition

`IterateLine` represents a **quantified logical constraint**:

### Universal Quantification (Default)
---
∀ child ∈ children(person): condition_set(child)
---

### Existential Quantification
--- 
∃ child ∈ children(person): condition_set(child)
---

## 3. Conceptual Model

`IterateLine` is:

- NOT a loop
- NOT graph node expansion
- NOT procedural iteration

It IS:

> A **declarative, quantified reasoning construct over a collection**


## 4. Core Structure

```python
class IterateLine:
    parent_ref: str           # e.g. "person"
    collection_ref: str       # e.g. "children"
    variable: str             # e.g. "child"
    condition_set: List[Rule]
    aggregation: str = "ALL"  # ALL | ANY | NONE | COUNT
```

## 5. Supported Aggregation Modes

| Mode  | Meaning                              |
| ----- | ------------------------------------ |
| ALL   | All entities must satisfy conditions |
| ANY   | At least one entity satisfies        |
| NONE  | No entities satisfy                  |
| COUNT | Threshold-based evaluation           |

## 6. Evaluation Strategy
#### Core Algorithm
```python

def evaluate_iterate(iterate_line, working_memory):
    entities = working_memory.get_collection(iterate_line.collection_ref)

    results = []
    for entity in entities:
        result = evaluate_condition_set(entity, iterate_line.condition_set)
        results.append(result)

    return aggregate(results, iterate_line.aggregation)
```
## 7. Performance Optimisation
### 7.1 Short-Circuit Evaluation
#### ALL
```python
for entity in entities:
    if not evaluate_condition_set(entity):
        return False
return True
```

#### ANY
```python
for entity in entities:
    if evaluate_condition_set(entity):
        return True
return False
```
### 7.2 Incremental Evaluation

#### When:

 - an entity is added/removed
 - an attribute changes

→ Only re-evaluate affected entities

### 7.3 Parallel Evaluation (Optional)

```python
parallel_map(evaluate_condition_set, entities)
```
## 8. Integration with Inference Engine
### Execution Point

IterateLine should be evaluated during:

    Backward-chaining node evaluation

### Important Constraints
 - Must remain a single logical node
 - Must NOT expand into multiple dependency nodes
 - Must NOT alter graph topology

## 9. Working Memory Design
#### Recommended Structure
```python
working_memory:
  - person:
    - children: [child1, child2]

  - child1:
    age: 20
  - child2:
    age: 15
```
#### iterate_cache:
```python
  "children.age>18.ALL": False
```

## 10. QuestionResolver Integration
### Problem

#### Naive approach:

- asks questions per entity → poor UX

### Recommended Strategy
#### Step 1: Detect missing facts
```python
missing_facts = find_missing_facts(entities, condition_set)
```
### Step 2: Ask grouped questions

Instead of:
```
 "Is child1 age > 18?"
 "Is child2 age > 18?"
```
#### Ask:
```
"Provide ages for all children"
```

#### Benefit
- reduces question volume
- improves user experience
- aligns with ontology-driven reasoning


## 11. Ontology Alignment (RDF / SPARQL)
#### Representation
```turtle
:child1 :hasParent :person ;
        :age 20 .

:child2 :hasParent :person ;
        :age 15 .
```
#### ALL Condition (SPARQL)
```sparql
ASK {
  ?child :hasParent :person .
  FILTER NOT EXISTS {
    ?child :age ?age .
    FILTER (?age <= 18)
  }
}
```
#### ANY Condition (SPARQL)
```sparql
ASK {
  ?child :hasParent :person .
  ?child :age ?age .
  FILTER (?age > 18)
}
```
#### Key Insight

Ontology layer can implicitly handle iteration

## 12. Explainability
#### Requirement

System must explain:
```
Why did the iteration pass or fail?
```
#### Example
```text
Rule: All children must be over 18
Result: FALSE

Details:
- child1: 20 → PASS
- child2: 15 → FAIL
```

## 13. Partial Evaluation Support
#### Scenario

Some entities lack required data

#### Result
```text
Result: UNKNOWN
```

#### Benefit
- integrates with question flow
- avoids premature failure


## 14. Key Design Principles
1. Treat IterateLine as quantified logic (∀ / ∃)
2. Keep it as a single evaluation unit
3. Avoid graph/node expansion
4. Support short-circuit evaluation
5. Enable batched question resolution
6. Maintain per-entity explainability
7. Leverage ontology for implicit iteration


## 15. Strategic Value

When implemented correctly, IterateLine becomes:
```text
A first-class reasoning primitive in INFERRA
```
It enables:

- expressive rule modelling
- efficient evaluation
- reduced user interaction
- seamless ontology integration

## 16. Summary

`IterateLine` transforms collection-based logic from:

- procedural iteration\
   → into
- declarative, quantified reasoning

It is a key building block in making INFERRA:

```
a hybrid reasoning system where logic, relationships, and inference converge.
```
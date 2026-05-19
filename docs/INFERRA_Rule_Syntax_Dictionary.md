# INFERRA Rule Syntax Dictionary
## Version 0.2 — Comprehensive Reference

**Purpose:** This dictionary provides an exhaustive explanation of every keyword, operator, and structural convention in the INFERRA rule syntax. It is written for rule engineers, engine developers, and non-technical stakeholders alike. Each entry explains what a keyword does in plain English, how it works technically, when to use it, when not to use it, and illustrates with real Australian legislative examples.

**How to Read This Dictionary:**
- Each keyword entry follows this structure:
  - **Syntax** — the exact pattern to write
  - **Plain English** — what it means for non-technical readers
  - **Technical Detail** — how the engine processes it
  - **When to Use** — the correct scenarios
  - **When NOT to Use** — common mistakes
  - **Examples** — real Australian legislative scenarios

---

## 1. Structural Overview

An INFERRA rule set is a plain-text file with three sections, always in this order:

```
FIXED declarations
INPUT declarations
Rule blocks (with # Reference / # Section / # Original comments)
```

**Plain English:** Think of an INFERRA rule set like a form with three parts:
1. **FIXED** = the pre-printed constants on the form (rates, dates, definitions that never change per rule set)
2. **INPUT** = the blank fields on the form (where a user will provide answers)
3. **Rule blocks** = the logic that determines the outcome (the "if this, then that" rules)

**Technical Detail:** At runtime, FIXED and INPUT entries populate the `FactValue` map (working memory). Rule blocks populate the `Node` map (dependency graph). The engine evaluates the dependency graph via backward chaining from a target goal.

---

## 2. Declaration Keywords

### 2.1 FIXED

**Syntax:**
```
FIXED <variable name> IS <value>
```

**Plain English:** FIXED declares a constant — a value that is known before the session starts and never changes. Think of it as a number printed in the legislation itself, like "the rate is $100" or "the threshold date is 1 July 1951".

**Technical Detail:**
- The variable name becomes a key in `Map<String, FactValue>` (the working memory / FactMap)
- The value is stored as a `FactValue` object and is immediately available without user input
- FIXED values are never asked as questions — they are pre-populated
- Supports values of type: text strings, numbers, dates, booleans

**When to Use:**
- Legislative rates, thresholds, and constants (e.g., maximum rates, cutoff dates)
- Enumerations that are defined in the legislation (e.g., "warlike service" as a category name)
- Any value that is fixed by the law and does not vary per client

**When NOT to Use:**
- For values that differ between users (use INPUT instead)
- For values that depend on other values (use IS CALC in a rule instead)
- For values that change over time (e.g., "today's date") — model these as INPUTs

**Examples:**

```
FIXED Act IS "Veterans' Entitlements Act 1986"
FIXED minimum distance threshold IS 50
FIXED long distance threshold IS 350
FIXED meals short distance rate IS 31.35
FIXED base date IS 1/7/1951
```

**Common Mistake:** Using FIXED for a value that should be computed. If the legislation says "the rate is 2% of the base amount", the rate depends on the base amount — use IS CALC in a rule, not FIXED.

---

### 2.2 INPUT

**Syntax:**
```
INPUT <variable name> AS <data type>
INPUT <variable name> AS <data type> IS <default value>
INPUT <variable name> AS LIST
    ITEM <value>
    ITEM <value>
INPUT <variable name> AS LIST AS LIST
    ITEM <value>
    ITEM <value>
```

**Plain English:** INPUT declares a question the engine will ask the user. It defines what kind of answer is expected (a yes/no, a number, a date, text, or a choice from a list). If a default value is provided with IS, that value is pre-filled but the user can change it.

**Technical Detail:**
- The variable name becomes a key in `Map<String, FactValue>` — just like FIXED
- However, unlike FIXED, INPUT values are NOT pre-populated; the engine will prompt the user for them during the session
- If `IS <default value>` is specified, the value is pre-populated but can be overridden by the user
- `AS LIST` defines a list where ITEMs are the valid choices
- `AS LIST AS LIST` defines a list of lists (a two-level list) — each ITEM is itself a list entry
- ITEM values are stored directly in the FactValue object, not as separate objects

**Data Types:**

| Type | Description | Example |
|------|-------------|---------|
| BOOLEAN | Yes/No (true/false) | `INPUT person is a veteran AS BOOLEAN` |
| NUMBER | Numeric value | `INPUT distance to treatment AS NUMBER` |
| DATE | Date value | `INPUT date of birth AS DATE` |
| TEXT | Free-text string | `INPUT person's name AS TEXT` |
| LIST | Selection from predefined options | `INPUT form of transport AS LIST` |

**When to Use:**
- For every value the user must provide during a session
- For values that differ between clients (name, date of birth, distance, etc.)
- For dropdown selections (use LIST with ITEM entries)

**When NOT to Use:**
- For constants defined in legislation (use FIXED instead)
- For computed values (use IS CALC in a rule instead)
- For values the engine can infer from other answers (those become rule conclusions)

**Examples:**

```
INPUT person served AS BOOLEAN
INPUT distance to treatment AS NUMBER
INPUT date of enlistment AS DATE
INPUT the member's rank AS TEXT
INPUT the boy's gender AS TEXT IS MALE
INPUT form of transport AS LIST
    ITEM car
    ITEM train
    ITEM plane
    ITEM bus
INPUT loan purpose AS LIST
    ITEM buy land and build house on land
    ITEM build house on land already owned
    ITEM renovate existing house
```

**Common Mistakes:**
1. Declaring an INPUT for a value that should be computed: `INPUT allowance amount AS NUMBER` — if the allowance is calculated from other inputs, it should be a rule with IS CALC, not an INPUT.
2. Using snake_case for variable names: `INPUT person_is_eligible AS BOOLEAN` — always use the exact legislative phrasing with spaces: `INPUT person is eligible AS BOOLEAN`.
3. Forgetting ITEM entries for LIST types — a LIST without ITEMs has no valid options.

---

### 2.3 AS

**Syntax:**
```
AS <data type>
```

**Plain English:** AS specifies what kind of data a variable holds. It appears in INPUT declarations.

**Technical Detail:** The data type determines:
- How the UI renders the question (checkbox for BOOLEAN, number input for NUMBER, date picker for DATE, text field for TEXT, dropdown for LIST)
- How the engine validates the user's answer
- How the value is stored in the FactValue object

**When to Use:** Always — every INPUT must have a data type specified with AS.

**When NOT to Use:** Never in rule blocks — AS is only valid in INPUT declarations.

---

### 2.4 IS (in Declarations)

**Syntax:**
```
FIXED <name> IS <value>
INPUT <name> AS <type> IS <default value>
```

**Plain English:** In declarations, IS assigns a value. For FIXED, it sets the constant. For INPUT, it sets a default value that is pre-filled.

**Technical Detail:**
- In FIXED: the value is immutable — it cannot be changed during the session
- In INPUT: the value is a default — the user can override it, but if they don't, this value is used
- The value after IS is stored as the FactValue for that key

**When to Use:**
- Always with FIXED (a constant without a value is meaningless)
- With INPUT when the legislation provides a default (e.g., "the gender is assumed to be MALE unless otherwise stated")

**When NOT to Use:**
- Do not use IS in INPUT declarations to set computed defaults — if the default depends on other values, handle it in the rule logic

---

### 2.5 ITEM

**Syntax:**
```
INPUT <name> AS LIST
    ITEM <value>
```

**Plain English:** ITEM defines one option in a list. If the INPUT is a dropdown menu, each ITEM is one choice on that menu.

**Technical Detail:**
- Each ITEM value is stored directly in the FactValue object for the parent list variable
- ITEMs are NOT separate objects — they are values within the list
- Indentation is critical: ITEM lines must be indented with 4 spaces under their parent INPUT
- If a line containing the keyword LIST is followed by indented lines, those lines are treated as ITEM entries unless the line is not indented

**When to Use:**
- Whenever an INPUT is declared AS LIST, you must define ITEM entries for the valid options
- For membership checks in rules using IS IN LIST (the list must be defined first)

**When NOT to Use:**
- Never use ITEM outside of a LIST declaration
- Never use inline lists like `[item1, item2]` — always define them as FIXED or INPUT lists with ITEM entries

**Examples:**

```
FIXED warlike service type AS LIST
    ITEM warlike service
    ITEM non-warlike service
    ITEM peacekeeping service
    ITEM hazardous service

INPUT service type AS LIST
    ITEM warlike service
    ITEM non-warlike service
    ITEM peacekeeping service
    ITEM hazardous service
```

**Common Mistake:** Using inline lists in rules. Wrong: `AND service type IS IN LIST: [warlike, non-warlike, peacekeeping]`. Correct: Define a FIXED or INPUT list with ITEM entries, then reference it: `AND service type IS IN LIST: warlike service type`.
---

## 3. Dependency Type Keywords

Dependency type keywords define the logical relationship between a parent rule and its child rules. They appear as the first word(s) on indented lines beneath a rule.

### 3.1 AND

**Syntax:**
```
<parent rule>
    AND <child rule>
    AND <child rule>
```

**Plain English:** AND means "all of these must be true". If the parent rule is to be satisfied, every AND child must also be satisfied. Think of it as a checklist — every item must be checked off.

**Technical Detail:**
- All AND children must evaluate to true for the parent to be true
- If any AND child evaluates to false, the entire AND group fails
- The engine evaluates all AND children and combines results with logical conjunction
- AND children are asked as questions in order (top to bottom)

**When to Use:**
- When the legislation uses "and", "also", "in addition", "must also", "both"
- When multiple conditions must ALL be satisfied simultaneously

**When NOT to Use:**
- When only ONE of several conditions needs to be met (use OR instead)
- When mixing with OR at the same indentation level (use a virtual node instead)

**Examples:**

```
# Reference: https://legislation.gov.au/xxx
# Section: Section 5A - Eligibility
# Original: A person is eligible if the person is a veteran AND has completed the qualifying period AND is an Australian resident

eligible person
    AND member of the Defence Force
    AND completed the basic service period
    AND is an Australian resident
```

```
# Original: The member qualifies for the allowance if the distance exceeds the minimum threshold and the member has a qualifying service type

the member qualifies for the allowance
    AND distance to treatment > minimum distance threshold
    AND service type IS IN LIST: qualifying service type
```

**Common Mistake:** Mixing AND and OR at the same indentation level. See Virtual Nodes (section 7.3) for how to handle this.

---

### 3.2 OR

**Syntax:**
```
<parent rule>
    OR <child rule>
    OR <child rule>
```

**Plain English:** OR means "any one of these will do". If ANY OR child is true, the parent is satisfied. Think of it as multiple paths to the same destination — you only need to take one.

**Technical Detail:**
- If any OR child evaluates to true, the entire OR group succeeds
- The engine evaluates OR children in order and can short-circuit on the first true result
- OR children represent alternative conditions — mutually exclusive or overlapping

**When to Use:**
- When the legislation uses "or", "either", "at least one of", "alternatively"
- When there are multiple independent ways to satisfy a condition

**When NOT to Use:**
- When ALL conditions must be met (use AND instead)
- When mixing with AND at the same indentation level (use a virtual node instead)

**Examples:**

```
# Original: A person is a veteran if the person served in warlike service or non-warlike service or peacekeeping service

the person is a veteran
    OR the person served in warlike service
    OR the person served in non-warlike service
    OR the person served in peacekeeping service
```

```
# Original: The claimant qualifies if they have a passport OR a driver's licence OR a birth certificate

the claimant qualifies
    OR the claimant has a passport
    OR the claimant has a driver's licence
    OR the claimant has a birth certificate
```

---

### 3.3 NOT

**Syntax:**
```
AND NOT <child rule>
OR NOT <child rule>
```

**Plain English:** NOT means "this must NOT be true". It flips the result of the child rule. If the child would be true, NOT makes it false, and vice versa.

**Technical Detail:**
- NOT is a modifier on a dependency type — it cannot appear alone
- `AND NOT` means: this child must be false for the parent to be true
- `OR NOT` means: this child being false is one way to satisfy the parent
- During self-evaluation, the engine inverts the boolean result of the child rule
- NOT can only appear on child rules — never on a parent rule

**When to Use:**
- When the legislation uses "not", "does not", "is not", "unless", "except when"
- When a condition must be absent (not present, not true, not met)

**When NOT to Use:**
- As a standalone keyword on a parent rule line (NOT can only modify a child dependency)
- When you really mean IS FALSE (prefer explicit IS FALSE for clarity in Value Conclusion lines)

**Examples:**

```
# Original: The person made it to Las Vegas, provided they did NOT miss the flight

the person made it to Las Vegas
    AND NOT the person missed the flight
```

```
# Original: The service does not qualify if the service type is NOT in the operational service list

service does not qualify
    AND NOT service type IS IN LIST: Operational service type
```

**Common Mistake:** Writing `NOT the person missed the flight` as a parent rule. NOT must be combined with AND or OR: `AND NOT the person missed the flight`.

---

### 3.4 KNOWN

**Syntax:**
```
AND KNOWN <variable name>
OR KNOWN <variable name>
```

**Plain English:** KNOWN means "has the user provided a value for this?" It checks whether a variable has been answered — not what the answer is, just that an answer exists. Think of it as "do we know this yet?"

**Technical Detail:**
- KNOWN checks if a value exists in the working memory for the specified variable
- It does NOT evaluate the truth/falsity of the value — only its presence
- `AND KNOWN x` is true if x has a value in working memory, false if x is missing
- `OR KNOWN x` is true if x has a value in working memory
- KNOWN can only appear on child rules — never on a parent rule
- Comparison Conclusion Lines do NOT support KNOWN (the engine auto-prompts for missing values)

**When to Use:**
- When the legislation says "if known", "where the value has been provided", "if the person has stated"
- When the rule logic needs to check whether a value has been collected, regardless of what the value is
- When you want to include a variable in the evaluation only if it has been answered

**When NOT to Use:**
- On Comparison Conclusion Lines (the engine handles missing values automatically)
- When you need to check the VALUE of a variable (use IS, =, >, etc.)
- As a parent rule modifier

**Examples:**

```
# Original: The person's identity is confirmed if we know the person's name AND we know the person's date of birth

Do we know the person's identity
    AND KNOWN the person's name
    AND KNOWN the person's date of birth
    OR we have the person's passport
```

**Common Mistake:** Confusing KNOWN with checking for a specific value. `AND KNOWN the person's name` checks if the name has been provided; `AND the person's name = "John"` checks what the name is.

---

### 3.5 MANDATORY

**Syntax:**
```
AND MANDATORY <child rule>
OR MANDATORY <child rule>
```

**Plain English:** MANDATORY means "the engine MUST ask this question and MUST get an answer before the session can converge (finish)". It marks a dependency as required — even if the logic could proceed without it, the engine insists on an answer.

**Technical Detail:**
- `AND MANDATORY` is equivalent to `NEEDS` in Expression Conclusion Lines
- Marks the dependency as required for convergence — the session will NOT converge if a MANDATORY dependency is unanswered
- The engine will always prompt for MANDATORY values, even if other conditions already determine the outcome
- `OR MANDATORY` marks this alternative as one that MUST be evaluated (but the parent can still be true if another OR branch is satisfied)

**When to Use:**
- When the legislation uses "must", "shall", "is required to", "mandatory"
- When a value is essential for the determination — the session cannot conclude without it
- When the rule requires a value to be asked even if other AND conditions already fail

**When NOT to Use:**
- When the condition is optional (use OPTIONALLY or no modifier)
- When you want the engine to skip asking if the answer is irrelevant (use no modifier or POSSIBLY)
- On Expression Conclusion Lines — use NEEDS instead (equivalent to AND MANDATORY)

**Examples:**

```
# Original: The person crossed the street, AND it is MANDATORY that the person is able to walk

the person did cross the street
    AND NOT the street was busy
    AND MANDATORY the person is able to walk
```

```
# Original: The client qualifies for the grant, AND it is MANDATORY that the client is an adult

the client qualifies for the grant
    OR the client needs the grant
    OR MANDATORY the client is an adult
```

**Plain English: AND MANDATORY vs plain AND:**
- Plain `AND`: The engine will ask this question, but if another AND child already fails, the engine might skip this one
- `AND MANDATORY`: The engine will ALWAYS ask this question, regardless of other AND children. The answer is required for the session to converge.

---

### 3.6 OPTIONALLY

**Syntax:**
```
AND OPTIONALLY <child rule>
OR OPTIONALLY <child rule>
```

**Plain English:** OPTIONALLY means "it would be nice to know this, but the session can finish without it". The engine will ask the question, but if the user doesn't answer, the session can still converge.

**Technical Detail:**
- The dependency is treated as relevant but not required for convergence
- The engine will include the question in the question flow, but the session can converge without an answer
- Weaker than MANDATORY — the absence of a value does not block convergence
- Useful for collecting supplementary information that enriches the outcome but isn't essential

**When to Use:**
- When the legislation says "may", "optionally", "if applicable"
- When the value improves the quality of the determination but isn't strictly required
- When you want the engine to ask the question but not block the session if it's unanswered

**When NOT to Use:**
- When the value is essential (use MANDATORY instead)
- When the value is completely irrelevant (don't include the rule at all)

**Examples:**

```
# Original: The claimant may provide a medical certificate (optional)

the claim is assessed
    AND MANDATORY the claimant has a qualifying condition
    AND OPTIONALLY the claimant has a medical certificate
```

---

### 3.7 POSSIBLY

**Syntax:**
```
AND POSSIBLY <child rule>
OR POSSIBLY <child rule>
```

**Plain English:** POSSIBLY means "this might be relevant, depending on other answers". It is the weakest level of dependency. The engine might ask the question, but it's not guaranteed, and the session can finish without it.

**Technical Detail:**
- The weakest dependency modifier — the engine may or may not prompt for this value
- The session can converge without this value being provided
- Useful for conditions that are only relevant in specific scenarios
- Weaker than OPTIONALLY — the engine has more discretion about whether to ask

**When to Use:**
- When the legislation says "might", "possibly", "could", "in some cases"
- When the relevance of the question depends on the answers to other questions
- When you want to allow the engine flexibility in whether to ask

**When NOT to Use:**
- When the value is required (use MANDATORY)
- When you want to ensure the question is always asked (use OPTIONALLY)
- When the value is completely irrelevant (don't include the rule)

**Examples:**

```
# Original: The veteran may possibly have a dependent child that affects the payment rate

the payment rate is determined
    AND MANDATORY the veteran's service type
    AND POSSIBLY the veteran has a dependent child
```

---

### 3.8 Combined Dependency Types

The keywords NOT, KNOWN, and MANDATORY/OPTIONALLY/POSSIBLY can be combined to express nuanced logical requirements. Below is every valid combination.

#### 3.8.1 AND NOT

**Syntax:** `AND NOT <child rule>`
**Meaning:** The child rule must be FALSE for the parent to be true.
**Example:**
```
the person is eligible
    AND NOT the person has a criminal record
```

#### 3.8.2 OR NOT

**Syntax:** `OR NOT <child rule>`
**Meaning:** The child rule being FALSE is one valid way to satisfy the parent.
**Example:**
```
the person is exempt
    OR NOT the person is required to lodge
    OR the person has a valid exemption
```

#### 3.8.3 AND KNOWN

**Syntax:** `AND KNOWN <variable name>`
**Meaning:** The variable MUST have a provided value (answered) for the parent to be true.
**Example:**
```
the identity is verified
    AND KNOWN the person's name
    AND KNOWN the person's date of birth
```

#### 3.8.4 OR KNOWN

**Syntax:** `OR KNOWN <variable name>`
**Meaning:** The variable having a provided value is one way to satisfy the parent.
**Example:**
```
Do we know the boy's identity
    AND KNOWN the boy's name
    AND KNOWN the boy's dob
    OR we have the boy's passport
```

#### 3.8.5 AND MANDATORY

**Syntax:** `AND MANDATORY <child rule>`
**Meaning:** Equivalent to NEEDS. The engine MUST ask this question and the session CANNOT converge without an answer.
**Example:**
```
the person did cross the street
    AND NOT the street was busy
    AND MANDATORY the person is able to walk
```

#### 3.8.6 OR MANDATORY

**Syntax:** `OR MANDATORY <child rule>`
**Meaning:** This alternative MUST be evaluated (the engine must ask this question), but the parent can still be true if another OR branch is satisfied. The question is asked regardless of other branches.
**Example:**
```
the client qualifies for the grant
    OR the client needs the grant
    OR MANDATORY the client is an adult
```

#### 3.8.7 MANDATORY NOT

**Syntax:** `AND MANDATORY NOT <child rule>` or `OR MANDATORY NOT <child rule>`
**Meaning:** The child rule must be FALSE, AND the engine must ask this question (the answer is required for convergence). Combines the enforcement of MANDATORY with the inversion of NOT.
**Example:**
```
the person is eligible for the pension
    AND MANDATORY NOT the person is receiving a comparable overseas pension
```

#### 3.8.8 POSSIBLY NOT

**Syntax:** `AND POSSIBLY NOT <child rule>` or `OR POSSIBLY NOT <child rule>`
**Meaning:** The child rule may or may not be false — if it is false, that contributes to the parent being true. The engine has discretion about whether to ask, and the session can converge without this being resolved.
**Example:**
```
the person qualifies for the concession
    AND POSSIBLY NOT the person has a disqualifying condition
```

#### 3.8.9 MANDATORY KNOWN

**Syntax:** `AND MANDATORY KNOWN <variable name>` or `OR MANDATORY KNOWN <variable name>`
**Meaning:** The variable MUST have a known value (the user MUST answer this question), AND the presence of the value contributes to the parent being true. Combines the enforcement of MANDATORY with the presence-check of KNOWN.
**Example:**
```
the application is complete
    AND MANDATORY KNOWN the applicant's tax file number
    AND MANDATORY KNOWN the applicant's residential address
```

#### 3.8.10 POSSIBLY KNOWN

**Syntax:** `AND POSSIBLY KNOWN <variable name>` or `OR POSSIBLY KNOWN <variable name>`
**Meaning:** The variable might have a known value — if it does, that contributes to the parent being true. The engine has discretion about whether to ask, and the session can converge without this being answered.
**Example:**
```
the assessment is complete
    AND POSSIBLY KNOWN the person's middle name
```

#### 3.8.11 MANDATORY NOT KNOWN

**Syntax:** `AND MANDATORY NOT KNOWN <variable name>` or `OR MANDATORY NOT KNOWN <variable name>`
**Meaning:** The variable MUST NOT have a known value — the engine requires confirmation that no value has been provided for this variable. This is used when the legislation requires that something is NOT known or NOT disclosed.
**Example:**
```
the person qualifies for the exemption
    AND MANDATORY NOT KNOWN the person's overseas income
```

#### 3.8.12 POSSIBLY NOT KNOWN

**Syntax:** `AND POSSIBLY NOT KNOWN <variable name>` or `OR POSSIBLY NOT KNOWN <variable name>`
**Meaning:** The variable might not have a known value — if it doesn't, that contributes to the parent being true. Weakest combination — the engine has full discretion.
**Example:**
```
the simplified assessment applies
    AND POSSIBLY NOT KNOWN the person's complex investment details
```

#### Dependency Modifier Strength Summary

| Modifier | Convergence | Engine Behaviour | Strength |
|----------|-------------|------------------|----------|
| MANDATORY | Session CANNOT converge without answer | Always asks, answer required | Strongest |
| (no modifier) | Session proceeds based on logic | Asks when relevant | Default |
| OPTIONALLY | Session CAN converge without answer | Always asks, but answer optional | Moderate |
| POSSIBLY | Session CAN converge without answer | May or may not ask | Weakest |

| Negation/Presence | Effect on Evaluation |
|-------------------|---------------------|
| NOT | Inverts the boolean result of the child |
| KNOWN | Checks for presence of a value, not the value itself |
| NOT KNOWN | Checks for absence of a value |
---

## 4. Rule Type Keywords

Rule type keywords define what kind of conclusion a rule draws. They appear on the parent rule line (not indented) and determine how the rule is evaluated.

### 4.1 IS (in Rules)

**Syntax:**
```
<variable name> IS <value>
```

**Plain English:** In rules, IS means "equals" or "has the value". It declares that a variable has a specific value. This is called a Value Conclusion Line.

**Technical Detail:**
- Creates a Value Conclusion Line node in the dependency graph
- During `selfEvaluation()`, checks if the variable's value matches the given value
- If the variable is a child rule, NOT and KNOWN modifiers can be applied
- If the rule is a parent, NOT and KNOWN cannot be applied
- Common forms: `A IS B`, `A IS TRUE`, `A IS FALSE`, `A IS IN LIST: B`

**When to Use:**
- When the legislation states that something IS a particular value
- When declaring a boolean conclusion (IS TRUE / IS FALSE)
- When checking membership in a list (IS IN LIST)

**When NOT to Use:**
- When comparing two variables (use `=` comparison instead)
- When performing arithmetic (use IS CALC instead)
- When the relationship is a comparison, not an equality (use >, <, >=, <=)

**Examples:**

```
# Original: The person's drinking habit is frequent drinker
the person's drinking habit IS frequent drinker
    AND number of drinks the person consumes a week > 3
    AND number of drinks the person consumes a week < 7
```

```
# Original: Part 2 creates no enforceable rights
part 2 creates no enforceable rights IS TRUE
```

```
# Original: The person's first name is MALE
the person's first name IS MALE
    AND the person's first name IS IN LIST: Male first name list
```

**Common Mistake:** Confusing IS with comparison. `the person's age IS 18` is a Value Conclusion (the age IS the value 18). `the person's age = 18` is a Comparison (comparing the age to 18). Use IS for declaring values, use = for comparing values.

**Important Rule:** A Value Conclusion Line with IS should NOT be a base child rule other than for plain statements. Use comparison (=, >, <) for child rules that compare values:

```
# WRONG:
Dean is a man
    AND Dean has a wife IS TRUE
    AND Dean is a kind man IS TRUE

# CORRECT:
Dean is a man
    AND Dean has a wife = TRUE
    AND Dean is a kind man = TRUE
```

---

### 4.2 IS TRUE / IS FALSE

**Syntax:**
```
<variable name> IS TRUE
<variable name> IS FALSE
```

**Plain English:** These are special forms of IS that declare a boolean value. IS TRUE means "this thing is true". IS FALSE means "this thing is false".

**Technical Detail:**
- Subset of Value Conclusion Lines
- During `selfEvaluation()`, checks if the variable's value is TRUE or FALSE
- Only valid as a parent rule or as a child rule with appropriate modifiers
- As a child rule, prefer using comparison (`= TRUE`, `= FALSE`) instead of IS TRUE / IS FALSE

**When to Use:**
- When the legislation states a boolean conclusion: "the person IS eligible", "the exemption IS FALSE"
- As a plain statement parent rule

**When NOT to Use:**
- As a child rule under another rule — use `= TRUE` or `= FALSE` comparison instead
- When you really mean the variable has a text value (use `IS "value"` instead)

**Examples:**

```
# Plain statement (parent):
part 2 creates no enforceable rights IS TRUE

# As a child, use comparison:
Dean is a man
    AND Dean has a wife = TRUE
    AND Dean is a kind man = TRUE
```

---

### 4.3 IS CALC

**Syntax:**
```
<variable name> IS CALC (<expression>)
    NEEDS <variable name>
    WANTS <variable name>
```

**Plain English:** IS CALC means "calculate this value using a formula". The expression inside the parentheses is evaluated to produce the result. Think of it as a spreadsheet formula — it computes the answer from other values.

**Technical Detail:**
- Creates an Expression Conclusion Line node in the dependency graph
- The expression inside `()` is evaluated using the values of referenced variables
- Supports arithmetic operators: `+`, `-`, `*`, `/`
- Supports conditional ternary operator: `condition ? value_if_true : value_if_false`
- Supports functions: `ROUND()`, `MAX()`, `MIN()`
- All variables used in the expression must be declared with NEEDS (mandatory) or WANTS (optional)
- IS CALC can be a parent or a child rule
- NEVER use IS CALC inside a child dependency — IS CALC must be the top-level statement of an Expression Conclusion Line
- Date arithmetic is NOT supported — model date logic externally and pass results as INPUTs

**When to Use:**
- When the legislation specifies a calculation: "the allowance is the rate multiplied by the number of days"
- When conditional logic is needed: "the rate is $100 if distance > 50, otherwise $50"
- When you need to compute a value from other variables

**When NOT to Use:**
- For simple boolean conclusions (use IS TRUE / IS FALSE)
- For comparing two values (use =, >, < comparison)
- For date calculations (INFERRA does not support date arithmetic)
- As a child dependency of another rule (IS CALC must be the top-level statement)

**Examples:**

```
# Original: The allowance is $100 if distance > 50, otherwise $50
allowance amount IS CALC (distance > threshold ? 100 : 50)
    NEEDS distance
```

```
# Original: The rectangle area is the height multiplied by the width
the rectangle area IS CALC (the rectangle height * the rectangle width)
    NEEDS the rectangle height
    NEEDS the rectangle width
```

```
# Original: The adjusted area is the height times the width if height is known, otherwise width times width
the another rectangle area IS CALC (the height ? (the height * the width : the width * the width))
    WANTS the height
    NEEDS the width
```

```
# Original: The travel allowance is the distance multiplied by the rate per kilometre
travel allowance IS CALC (distance to treatment * rate per kilometre)
    NEEDS distance to treatment
    NEEDS rate per kilometre
```

**Common Mistakes:**
1. Using IF...THEN...ELSE inside IS CALC — use the ternary operator `? :` instead
2. Using IS CALC inside a child dependency — IS CALC must always be the top-level statement
3. Forgetting NEEDS/WANTS declarations for variables used in the expression
4. Attempting date arithmetic — model date logic externally and pass results as INPUTs

---

### 4.4 IS IN LIST

**Syntax:**
```
<variable name> IS IN LIST: <list name>
```

**Plain English:** IS IN LIST means "is this value one of the options in this list?" It checks whether a variable's value matches any of the ITEMs defined in a FIXED or INPUT list. Think of it as checking a dropdown selection against a predefined menu.

**Technical Detail:**
- Creates a Value Conclusion Line with a list membership check
- The list name must reference a FIXED or INPUT declaration that has ITEM entries
- During `selfEvaluation()`, checks if the variable's value exists in the specified list
- The colon (`:`) is a required separator between `LIST` and the list name
- Can be combined with NOT: `AND NOT service type IS IN LIST: Operational service type`

**When to Use:**
- When the legislation defines a set of valid options and you need to check membership
- When the legislation uses "is one of", "is included in", "is classified as"
- When checking against enumerated categories (e.g., service types, claim types, residency statuses)

**When NOT to Use:**
- For inline lists — never write `[item1, item2]` in a rule
- For simple equality checks (use `=` instead)
- For range checks (use >= and <= instead)

**Examples:**

```
# First, define the list:
FIXED Operational service type AS LIST
    ITEM warlike service
    ITEM non-warlike service

# Then, use IS IN LIST in a rule:
the service qualifies
    AND service type IS IN LIST: Operational service type
```

```
# Original: The person's first name is in the male first name list
the person's first name IS MALE
    AND the person's first name IS IN LIST: Male first name list
```

```
# With NOT — checking that something is NOT in a list:
AND NOT service type IS IN LIST: Operational service type
```

**Common Mistake:** Using inline lists. Wrong: `AND service type IS IN LIST: [warlike, non-warlike]`. Correct: Define a FIXED list with ITEM entries, then reference it.

---

### 4.5 Comparison Operators (=, >, <, >=, <=)

**Syntax:**
```
<variable name> = <value>
<variable name> > <value>
<variable name> < <value>
<variable name> >= <value>
<variable name> <= <value>
```

**Plain English:** Comparison operators compare two values. They ask "is A equal to B?", "is A greater than B?", etc. If a value is missing, the engine will ask the user for it.

**Technical Detail:**
- Creates a Comparison Conclusion Line node in the dependency graph
- Compares two values — either literals (in double quotes) or variable names
- If a value is missing from working memory, the engine automatically prompts the user
- Result is stored in working memory as a boolean FactValue
- Only valid as a child rule — cannot be a parent rule
- Comparison lines do NOT need explicit NEEDS declarations — the engine auto-prompts for missing values
- Can be combined with NOT: `AND NOT the person's age > 65`

**Literal vs Variable Comparison:**
- If a value is in double quotes (e.g., `"MALE"`), it compares against a literal string
- If a value is not in quotes (e.g., `another person's last name`), it compares against another variable's value
- Example: `the person's first name = "MALE"` compares the variable value to the literal "MALE"
- Example: `the person's last name = another person's last name` compares two variable values

**When to Use:**
- When the legislation uses "exceeds", "is greater than", "is less than", "equals", "is at least"
- When comparing a variable against a threshold, a fixed value, or another variable
- As a child rule (comparison lines cannot be parent rules)

**When NOT to Use:**
- As a parent rule (comparison lines can only be children)
- When declaring a value (use IS instead)
- When performing arithmetic (use IS CALC instead)

**Examples:**

```
# Original: The person is a son of another person if the person's first name is MALE and the person's last name equals another person's last name
the person is a son of another person
    AND the person's first name = "MALE"
    AND the person's last name = another person's last name
    AND NOT the person = another person
```

```
# Original: The service qualifies if the enlistment date is on or after 1 July 1951 and the discharge date is on or before 6 December 1972
the service qualifies
    AND enlistment date >= 1/7/1951
    AND discharge date <= 6/12/1972
```

```
# Original: The person qualifies if the distance is greater than the minimum threshold
the person qualifies
    AND distance to treatment > minimum distance threshold
```

---

### 4.6 Ternary Operator (? :)

**Syntax:**
```
<condition> ? <value_if_true> : <value_if_false>
```

**Plain English:** The ternary operator is INFERRA's way of saying "if this, then that, otherwise something else". It replaces IF...THEN...ELSE statements. The condition is checked first; if true, the first value is used; if false, the second value is used.

**Technical Detail:**
- Only valid inside IS CALC expressions
- The condition can be any comparison expression (using =, >, <, >=, <=)
- The values can be numbers, variable references, or nested ternary expressions
- INFERRA does NOT support IF...THEN...ELSE — always use the ternary operator instead
- Can be nested for multiple conditions

**When to Use:**
- When the legislation specifies conditional values: "the rate is X if condition A, otherwise Y"
- When you need IF...THEN...ELSE logic — always use the ternary operator instead
- For branching calculations within IS CALC

**When NOT to Use:**
- Outside of IS CALC expressions
- As a replacement for OR/AND branching — use OR/AND for logical conditions, ternary for value selection
- For complex multi-way branching (prefer separate rules with OR for readability)

**Examples:**

```
# Original: The allowance is $100 if distance > 50, otherwise $50
allowance amount IS CALC (distance > threshold ? 100 : 50)
    NEEDS distance
```

```
# Original: The rate depends on the distance: short distance rate if <= 350, long distance rate if > 350
travel rate IS CALC (distance to treatment <= long distance threshold ? meals short distance rate : meals long distance rate)
    NEEDS distance to treatment
    NEEDS meals short distance rate
    NEEDS meals long distance rate
```

**Common Mistake:** Using IF...THEN...ELSE syntax. Wrong: `IF distance > 50 THEN 100 ELSE 50`. Correct: `distance > threshold ? 100 : 50`.

---

### 4.7 Functions (ROUND, MAX, MIN)

**Syntax:**
```
ROUND(<expression>)
MAX(<expression>, <expression>)
MIN(<expression>, <expression>)
```

**Plain English:** These are built-in helper functions for calculations inside IS CALC:
- **ROUND** — rounds a number to the nearest whole number (or specified decimal places)
- **MAX** — returns the larger of two values
- **MIN** — returns the smaller of two values

**Technical Detail:**
- Only valid inside IS CALC expressions
- ROUND, MAX, MIN are the only supported functions
- Date functions are NOT supported — model date logic externally

**When to Use:**
- ROUND: when the legislation specifies rounding (e.g., "rounded to the nearest cent")
- MAX: when the legislation says "the greater of" or "at least"
- MIN: when the legislation says "the lesser of" or "at most"

**When NOT to Use:**
- Outside of IS CALC expressions
- For date calculations

**Examples:**

```
# Original: The payment amount is rounded to the nearest cent
payment amount IS CALC (ROUND(base amount * rate))
    NEEDS base amount
    NEEDS rate
```

```
# Original: The benefit is the greater of the calculated amount and the minimum benefit
benefit amount IS CALC (MAX(calculated amount, minimum benefit))
    NEEDS calculated amount
    NEEDS minimum benefit
```
---

## 5. Expression Keywords

### 5.1 NEEDS

**Syntax:**
```
<variable name> IS CALC (<expression>)
    NEEDS <variable name>
    NEEDS <variable name>
```

**Plain English:** NEEDS means "this variable MUST be provided for the calculation to work". It is the same as AND MANDATORY — the engine will always ask for this value and the session cannot converge without it.

**Technical Detail:**
- Equivalent to `AND MANDATORY` dependency type
- Marks a variable as required for the expression's evaluation
- The engine will always prompt for NEEDS values, even if other conditions already determine the outcome
- Only valid under IS CALC (Expression Conclusion Lines)
- The variable referenced in NEEDS must be declared as INPUT or FIXED, or be the name of another rule

**When to Use:**
- When a variable is essential for the IS CALC expression — the calculation cannot proceed without it
- When the legislation requires the value to be known
- For every variable in the expression that must have a value for the result to be meaningful

**When NOT to Use:**
- When the variable is optional (use WANTS instead)
- Outside of IS CALC expression blocks
- On Comparison Conclusion Lines (the engine auto-prompts for missing values)

**Examples:**

```
the rectangle area IS CALC (the rectangle height * the rectangle width)
    NEEDS the rectangle height
    NEEDS the rectangle width
```

```
allowance amount IS CALC (distance > threshold ? 100 : 50)
    NEEDS distance
```

**Common Mistake:** Forgetting NEEDS for variables used in the IS CALC expression. Every variable that the expression references should be declared with either NEEDS (required) or WANTS (optional).

---

### 5.2 WANTS

**Syntax:**
```
<variable name> IS CALC (<expression>)
    WANTS <variable name>
    NEEDS <variable name>
```

**Plain English:** WANTS means "it would be nice to have this value, but the calculation can work without it". It is the same as OR — the engine will try to get the value, but if it's not available, the expression still evaluates (using a default or fallback).

**Technical Detail:**
- Equivalent to `OR` dependency type
- Marks a variable as optional for the expression's evaluation
- If the variable is not provided, the expression uses the fallback path in the ternary operator
- Only valid under IS CALC (Expression Conclusion Lines)
- Typically used with ternary expressions where the WANTS variable appears in the condition part

**When to Use:**
- When a variable is used in the condition of a ternary expression but has a fallback
- When the calculation can produce a valid result even without this value
- When the legislation says "if known" or "if available" for a calculation input

**When NOT to Use:**
- When the variable is essential (use NEEDS instead)
- Outside of IS CALC expression blocks
- For variables that must always be present

**Examples:**

```
# Original: The area is height * width if height is known, otherwise width * width
the another rectangle area IS CALC (the height ? (the height * the width : the width * the width))
    WANTS the height
    NEEDS the width
```

In this example:
- `the width` is NEEDS — the calculation absolutely requires it
- `the height` is WANTS — if available, it's used; if not, the fallback `width * width` is used

---

### NEEDS vs WANTS Summary

| Aspect | NEEDS | WANTS |
|--------|-------|-------|
| Equivalent to | AND MANDATORY | OR |
| Engine asks? | Always | Only if relevant |
| Session converges without? | No | Yes |
| Use when | Value is essential | Value is optional |
| Typical use | Core calculation inputs | Conditional/fallback values |

---

## 6. Iteration Keywords

### 6.1 ITERATE

**Syntax:**
```
<quantifier> <variable name> ITERATE: LIST OF <list name>
    <child rules follow immediately>
```

**Plain English:** ITERATE means "go through each item in this list and check the conditions". It is like a loop — for every item in a list (e.g., every service record in a person's service history), the engine evaluates the child rules.

**Technical Detail:**
- Creates an Iterate Line node in the dependency graph
- The engine iterates over each item in the specified list and evaluates the child rules for each item
- Child rules must be defined immediately below the ITERATE line (with proper indentation)
- Only valid as a child rule — cannot be a parent rule
- The quantifier determines how many items must pass the conditions (see ALL, NONE below)
- Can be combined with NOT for negation

**When to Use:**
- When the legislation refers to "each" or "every" item in a collection
- When a person can have multiple records (e.g., multiple periods of service, multiple dependants)
- When the same conditions must be checked for each item in a list

**When NOT to Use:**
- When there is only one item (use a simple rule instead)
- When the conditions don't involve iterating over a collection
- As a parent rule

**Examples:**

```
# Original: Check each service record in the person's service history
NOT ALL service ITERATE: LIST OF service history
    OR one
        AND enlistment date >= 01/07/1951
        AND discharge date <= 06/12/1972
        AND NOT service type IS IN LIST: Operational service type
    OR two
        AND enlistment date >= 07/04/1994
```

**Common Mistake:** Defining child rules separately from the ITERATE line. Child rules must follow immediately after ITERATE with proper indentation.

---

### 6.2 LIST OF

**Syntax:**
```
<quantifier> <variable name> ITERATE: LIST OF <list name>
```

**Plain English:** LIST OF specifies which list the ITERATE should loop over. It references a FIXED or INPUT list by name.

**Technical Detail:**
- The list name must reference a FIXED or INPUT declaration with ITEM entries
- The list must be defined before it is referenced in an ITERATE statement
- The ITEMS in the list become the individual records that the iteration processes

**When to Use:**
- Always paired with ITERATE — you cannot have ITERATE without LIST OF

**When NOT to Use:**
- Outside of ITERATE statements

---

### 6.3 ALL

**Syntax:**
```
ALL <variable name> ITERATE: LIST OF <list name>
```

**Plain English:** ALL means "every single item in the list must pass the conditions". Think of it as a universal quantifier — "for ALL items, this must be true".

**Technical Detail:**
- The iteration evaluates to TRUE only if ALL items in the list satisfy the child conditions
- If any single item fails, the entire ALL evaluates to FALSE
- Can be combined with NOT: `NOT ALL` means "not every item passes" (i.e., at least one fails)
- Equivalent to logical AND across all items in the list

**When to Use:**
- When the legislation says "all", "every", "each and every", "all without exception"
- When every record must meet the criteria

**When NOT to Use:**
- When only some items need to pass (use a number or NONE instead)
- When you need at least one to pass (omit ALL or use NOT NONE)

**Examples:**

```
# Original: ALL service records must meet the qualifying criteria
ALL service ITERATE: LIST OF service history
    AND service type IS IN LIST: Qualifying service type
    AND period of service >= minimum period
```

```
# Original: NOT ALL service records are non-qualifying (i.e., at least one IS qualifying)
NOT ALL service ITERATE: LIST OF service history
    OR one
        AND enlistment date >= 01/07/1951
        AND discharge date <= 06/12/1972
```

---

### 6.4 NONE

**Syntax:**
```
NONE <variable name> ITERATE: LIST OF <list name>
```

**Plain English:** NONE means "not a single item in the list passes the conditions". Think of it as "for NONE of the items is this true".

**Technical Detail:**
- The iteration evaluates to TRUE only if NO items in the list satisfy the child conditions
- If any single item passes, the entire NONE evaluates to FALSE
- Equivalent to `NOT ALL` with inverted child conditions
- Can be combined with NOT: `NOT NONE` means "at least one passes"

**When to Use:**
- When the legislation says "none", "no", "not a single", "zero"
- When no record should meet the criteria

**When NOT to Use:**
- When you need at least one to pass (use ALL with NOT, or a positive number)
- When you need every item to pass (use ALL instead)

**Examples:**

```
# Original: NONE of the service records qualify as operational service
NONE service ITERATE: LIST OF service history
    AND service type IS IN LIST: Operational service type
```

---

### 6.5 Number Quantifier

**Syntax:**
```
<number> <variable name> ITERATE: LIST OF <list name>
```

**Plain English:** A number quantifier means "at least this many items must pass the conditions". For example, `3 service ITERATE: LIST OF service history` means "at least 3 service records must meet the criteria".

**Technical Detail:**
- The iteration evaluates to TRUE if the specified number (or more) of items satisfy the child conditions
- Example: `2 service ITERATE: LIST OF service history` requires at least 2 qualifying records

**When to Use:**
- When the legislation specifies a minimum count: "at least 3 periods of service"
- When you need a specific number of qualifying records

**When NOT to Use:**
- When you need ALL items to pass (use ALL)
- When you need NO items to pass (use NONE)

---

### Iteration Quantifier Summary

| Quantifier | Meaning | Evaluates TRUE when |
|------------|---------|---------------------|
| ALL | Every item must pass | All items satisfy conditions |
| NONE | No item must pass | Zero items satisfy conditions |
| NOT ALL | At least one must fail | Not every item satisfies conditions |
| NOT NONE | At least one must pass | At least one item satisfies conditions |
| `<N>` | At least N must pass | N or more items satisfy conditions |

---

## 7. Structural Conventions

### 7.1 Indentation

**Rule:** Use 4-space indentation for child rules. Each level of nesting adds 4 spaces.

**Plain English:** Indentation shows which rules are children of which parent. Just like an outline:
- A parent rule has no indentation
- Its children are indented 4 spaces
- Their children are indented 8 spaces
- And so on

**Technical Detail:**
- 4-space indentation determines the parent-child relationship in the dependency graph
- The engine uses indentation to build the tree structure of rules
- Mixed tabs and spaces will cause errors — always use spaces
- ITEM entries under LIST declarations also use 4-space indentation

**Common Mistake:** Using 2-space or tab indentation. Always use 4 spaces.

---

### 7.2 Comment Blocks

**Rule:** Every rule block MUST be preceded by three comment lines:

```
# Reference: [URL or document reference]
# Section: [Section title or number]
# Original: [Exact legislative text being modeled]
```

**Plain English:** Every rule must have a citation showing:
1. Where in the law it comes from (Reference)
2. Which section of the law (Section)
3. The exact words from the law (Original)

**Technical Detail:**
- These are metadata comments — the engine does not evaluate them
- They are required for traceability and auditability
- The Original text should be the exact wording from the legislation, not a paraphrase
- Comments start with `#` (hash symbol)

**When to Use:** Before EVERY rule block — no exceptions.

**Examples:**

```
# Reference: https://legislation.gov.au/series/C2004A01321
# Section: Section 5A - Qualifying service
# Original: A person has qualifying service if the person has rendered warlike service
the person has qualifying service
    OR the person has rendered warlike service
    OR the person has rendered non-warlike service
```

---

### 7.3 Virtual Nodes

**Rule:** When a parent rule has both AND and OR children at the same indentation level, you MUST create a virtual node to ensure correct logical evaluation.

**Plain English:** If a rule needs both "all of these" (AND) and "any of these" (OR) at the same level, the engine gets confused. You need to create a helper group (virtual node) that bundles one side together, so the logic is clear.

**Technical Detail:**
- Virtual nodes are automatically created by the engine when AND and OR are mixed at the same level
- However, the official guidance recommends creating them explicitly for clarity
- Virtual nodes are NOT visible to the user — they are structural aids for the engine
- Name virtual nodes descriptively: e.g., "attendant scenario one", "distance condition met"
- Virtual nodes appear in the NodeMap but not in the question flow

**When to Use:**
- When a rule needs both AND and OR children at the same level
- When multiple conditions are chained at the same level under OR/AND without grouping

**When NOT to Use:**
- When the rule has only AND or only OR children (no virtual node needed)
- When the logic is already clear with proper nesting

**Examples:**

```
# WRONG — ambiguous AND/OR mixing:
meals only reimbursement
    OR meals required AND number of nights = 0 AND distance to treatment > minimum distance threshold
        AND meals only reimbursement = meals short distance rate

# CORRECT — with virtual nodes:
meals only reimbursement
    OR meals required virtual one
        AND meals required
        AND number of nights = 0
        AND distance to treatment > minimum distance threshold
        AND distance to treatment <= long distance threshold
        AND meals only reimbursement = meals short distance rate
    OR meals condition not met
        AND meals only reimbursement = 0
```

---

### 7.4 Naming Conventions

**Rules:**
1. NEVER use snake_case (e.g., `person_is_eligible`)
2. ALWAYS use the exact terminology from the legislation, with spaces (e.g., `eligible person`, `completed the basic service period`)
3. Do not reword or abbreviate legislative terms

**Plain English:** Variable names should be the exact phrases from the law, with spaces instead of underscores. This makes the rules readable by non-technical people and ensures they match the legislation exactly.

**Technical Detail:**
- Variable names are used as keys in both the FactMap (`Map<String, FactValue>`) and the NodeMap (`Map<String, Node>`)
- Spaces in variable names are valid — the engine treats the entire text between keywords as the variable name
- The same variable name in different rules refers to the SAME variable (shared reference)
- Descriptive names with spaces are preferred for readability and legislative traceability

**Examples:**

```
# WRONG:
person_is_eligible
    AND has_completed_service
    AND distance_to_treatment > minimum_distance

# CORRECT:
eligible person
    AND completed the basic service period
    AND distance to treatment > minimum distance threshold
```

---

### 7.5 Literal vs Variable Values

**Rule:**
- If a value is in double quotation marks (e.g., `"MALE"`), it is a **literal** — the engine compares against the exact text
- If a value is NOT in quotes (e.g., `another person's last name`), it is a **variable** — the engine compares against that variable's current value

**Examples:**

```
# Literal comparison — compares the value of "the person's first name" to the literal string "MALE"
AND the person's first name = "MALE"

# Variable comparison — compares the value of "the person's last name" to the value of "another person's last name"
AND the person's last name = another person's last name
```

**Technical Detail:**
- Literal values in quotes are treated as strings, regardless of content
- Variable values are looked up in the working memory (FactMap)
- If the variable name `the person's first name` has value `John` and the comparison is against `"Tony"`, the engine compares `"John"` = `"Tony"` (false)
- If the variable name `the person's last name` has value `Smith` and the comparison is against `another person's last name` with value `Smith`, the engine compares `"Smith"` = `"Smith"` (true)---

## 8. Rule Types Deep Dive

### 8.1 Value Conclusion Line

**Syntax:**
```
<variable name> IS <value>
<variable name> IS TRUE
<variable name> IS FALSE
<variable name> IS IN LIST: <list name>
```

**Plain English:** A Value Conclusion Line declares that a variable has a specific value. It is the simplest kind of rule -- `X IS Y`. The simplest form is a plain statement (just the variable name), which the engine will ask the user about.

**Sub-types:**

| Form | Example | Description |
|------|---------|-------------|
| Plain statement | `Dean is a man` | The engine asks the user a yes/no question |
| IS value | `the person's drinking habit IS frequent drinker` | Declares the variable equals a specific value |
| IS TRUE | `part 2 creates no enforceable rights IS TRUE` | Declares a boolean true |
| IS FALSE | `the gender is accepted IS FALSE` | Declares a boolean false |
| IS IN LIST | `service type IS IN LIST: Operational service type` | Checks list membership |

**Key Rules:**
1. As a parent: cannot use NOT or KNOWN modifiers
2. As a child: can use NOT, KNOWN, MANDATORY, OPTIONALLY, POSSIBLY and their combinations
3. Should NOT be used as a base child rule for comparisons -- use Comparison Conclusion Lines (`= TRUE`) instead
4. Plain statements (no IS keyword) are valid and common -- the engine will prompt the user

**Critical Rule:** When used as a child, prefer comparison syntax (`= TRUE`, `= FALSE`) instead of IS TRUE / IS FALSE:

```
# WRONG -- IS TRUE as child dependency:
Dean is a man
    AND Dean has a wife IS TRUE
    AND Dean is a kind man IS TRUE

# CORRECT -- comparison as child dependency:
Dean is a man
    AND Dean has a wife = TRUE
    AND Dean is a kind man = TRUE
    AND Dean was born as a man
```

**Why?** As a child rule, the engine determines the value by either asking a question or checking working memory. The comparison form (`= TRUE`) is the proper way to express this as a child dependency.

---

### 8.2 Comparison Conclusion Line

**Syntax:**
```
<variable name> = <value>
<variable name> > <value>
<variable name> < <value>
<variable name> >= <value>
<variable name> <= <value>
```

**Plain English:** A Comparison Conclusion Line compares two values. If a value is missing, the engine will ask the user for it automatically.

**Technical Detail:**
- Compares two values (literal or variable)
- If a value is missing, the engine prompts the user -- do NOT add NEEDS for comparison lines
- Result is stored in working memory
- Only valid as a child rule -- cannot be a parent
- Supports modifiers: NOT, MANDATORY, OPTIONALLY, POSSIBLY and their combinations
- Does NOT support KNOWN (the engine auto-prompts, making KNOWN redundant)

**When to Use vs Value Conclusion:**
- Use Comparison when checking a relationship (equals, greater than, less than)
- Use Value Conclusion (IS) when declaring what something IS

**Common Mistake:** Adding NEEDS to comparison lines. The engine automatically prompts for missing values in comparisons -- NEEDS is only for IS CALC expressions.

---

### 8.3 Expression Conclusion Line

**Syntax:**
```
<variable name> IS CALC (<expression>)
    NEEDS <variable name>
    WANTS <variable name>
```

**Plain English:** An Expression Conclusion Line calculates a value using a formula. The expression inside the parentheses is evaluated to produce the result.

**Technical Detail:**
- Evaluates expressions in parentheses
- Supports arithmetic: `+`, `-`, `*`, `/`
- Supports conditional: `condition ? value_if_true : value_if_false`
- Supports functions: `ROUND()`, `MAX()`, `MIN()`
- Can be a parent rule or a child rule
- All variables in the expression must be declared with NEEDS (mandatory) or WANTS (optional)
- NEVER use IS CALC inside a child dependency -- IS CALC must be the top-level statement

**Critical Rule:** When IS CALC is used as a child rule, it should be extracted to a separate rule block:

```
# WRONG -- IS CALC inside a child dependency:
Dean is a man
    AND Dean's age IS CALC (today's date - Dean's dob)
        NEEDS Dean's dob
    AND Dean has a wife = TRUE

# CORRECT -- IS CALC as a separate rule:
Dean is a man
    AND Dean's age > 18
    AND Dean has a wife = TRUE
    AND Dean was born as a man

Dean's age IS CALC (today's date - Dean's dob)
    NEEDS Dean's dob
```

**Why?** IS CALC must be the top-level statement of an Expression Conclusion Line. When it appears as a child dependency, it creates an ambiguous structure. Extract the calculation to a separate rule block and reference the result in the parent rule.

---

### 8.4 Iterate Line

**Syntax:**
```
<quantifier> <variable name> ITERATE: LIST OF <list name>
    <child rules>
```

**Plain English:** An Iterate Line loops through each item in a list and evaluates conditions for each one. It is the INFERRA equivalent of a `for each` loop in programming.

**Technical Detail:**
- Iterates over each item in the specified list
- Child rules are evaluated for EACH item in the list
- Quantifiers: ALL, NONE, or a number (minimum count)
- Can be combined with NOT for negation
- Only valid as a child rule
- Child rules must follow immediately with proper indentation
- Does NOT support KNOWN modifier

**When to Use:**
- When a person can have multiple records of the same type
- When the legislation says `each`, `every`, `any`, `at least N`
- For service history, dependant lists, claim records, etc.

**Complete Example:**

```
# Original: A person must meet military service criteria if NOT ALL of their service records fail the qualifying conditions
person must meet military service criteria
    AND NOT ALL service ITERATE: LIST OF service history
        AND iterate rules
            OR one
                AND enlistment date >= 01/07/1951
                AND discharge date <= 06/12/1972
                AND NOT service type IS IN LIST: Operational service type
            OR two
                AND enlistment date >= 22/05/1986
                AND yearly period of service by 06/04/1994 >= 3
```

---

### 8.5 Virtual Line

**Plain English:** A Virtual Line is a helper rule that the engine creates automatically when a parent rule has both AND and OR children at the same level. It ensures the logic is grouped correctly.

**Technical Detail:**
- Auto-generated by the engine -- not written in the rule file
- Invisible to the user
- Ensures correct logical grouping when AND and OR are mixed
- Can also be explicitly created by the rule engineer for clarity
- Can be a parent (but never a child)
- Always evaluated during self-evaluation

**Example of Auto-Generation:**

```
# What you write:
person must meet military service criteria
    AND number of services
    OR one
        AND enlistment date >= 01/07/1951
        AND discharge date <= 06/12/1972
    OR two
        AND enlistment date >= 22/05/1986

# What the engine creates internally:
person must meet military service criteria
    OR VirtualNode - person must meet military service criteria
        AND number of services
    OR one
        AND enlistment date >= 01/07/1951
        AND discharge date <= 06/12/1972
    OR two
        AND enlistment date >= 22/05/1986
```

**Best Practice:** Create virtual nodes explicitly in your rule file rather than relying on the engine to auto-generate them. This makes the logic clearer and prevents unexpected evaluation order.
---

## 9. Rule Type Matrix (Expanded)

The following table describes the characteristics of each rule type in the INFERRA Inference Engine. It distinguishes between behavior in the **Rule Format** (as written in rule files) and **Rule Structure** (as represented internally in the engine).

| Rule Type | Option / Keyword | In Rule Format | In Rule Structure | Can Be Child | Can Be Parent | Needs Self-Eval |
|-----------|-----------------|----------------|-------------------|--------------|---------------|-----------------|
| **Value Conclusion** | No Keywords | Yes | Yes | Yes | Yes | Only if not plain |
| | NOT | Yes | Yes | Yes | No | Yes |
| | KNOWN | Yes | Yes | Yes | No | Yes |
| | MANDATORY | Yes | Yes | Yes | Yes | No |
| | OPTIONALLY | Yes | Yes | Yes | Yes | No |
| | POSSIBLY | Yes | Yes | Yes | Yes | No |
| | MANDATORY NOT | Yes | Yes | Yes | No | Yes |
| | POSSIBLY NOT | Yes | Yes | Yes | No | Yes |
| | MANDATORY KNOWN | Yes | Yes | Yes | No | Yes |
| | POSSIBLY KNOWN | Yes | Yes | Yes | No | Yes |
| | MANDATORY NOT KNOWN | Yes | Yes | Yes | No | Yes |
| | POSSIBLY NOT KNOWN | Yes | Yes | Yes | No | Yes |
| **Comparison** | No Keywords | Yes | Yes | Yes | No | Yes |
| | NOT | Yes | Yes | Yes | Yes | Yes |
| | KNOWN | No | No | No | No | No |
| | MANDATORY | Yes | Yes | Yes | No | No |
| | OPTIONALLY | Yes | Yes | Yes | No | No |
| | POSSIBLY | Yes | Yes | Yes | No | No |
| | MANDATORY NOT | Yes | Yes | Yes | No | Yes |
| | POSSIBLY NOT | Yes | Yes | Yes | No | Yes |
| | Others | No | No | No | No | No |
| **Expression** | No Keywords | Yes | Yes | Yes | Yes | Yes |
| | NOT | Yes | Yes | Yes | No | Yes |
| | KNOWN | No | No | No | No | No |
| | NEEDS (same as MANDATORY) | Yes | Yes | Yes | No | No |
| | WANTS (same as OR) | Yes | Yes | Yes | No | No |
| | Others | No | No | No | No | No |
| **Iterate** | ALL, NONE, or number | Yes | Yes | Yes | No | Yes |
| | NOT | Yes | Yes | Yes | No | Yes |
| | KNOWN | No | No | No | No | No |
| | MANDATORY | Yes | Yes | Yes | No | No |
| | OPTIONALLY | Yes | Yes | Yes | No | No |
| | POSSIBLY | Yes | Yes | Yes | No | No |
| | Others | No | No | No | No | No |
| **Virtual** | Auto-generated | No | Yes | No | Yes | Yes |

**Key Takeaways from the Matrix:**
- Virtual Rules are the only type that exist in the engine structure but not in the rule file
- KNOWN is NOT supported on Comparison, Expression, or Iterate lines
- NOT can appear on most child rules but has limited parent rule support
- NEEDS and WANTS are specific to Expression lines and are equivalent to MANDATORY and OR respectively
- A rule that `Needs Self-Eval = Yes` will have its value checked during the evaluation cycle
- A rule that `Needs Self-Eval = No` is a structural dependency modifier (like MANDATORY) that controls question flow but does not evaluate a boolean condition itself

---

## 10. Common Patterns and Anti-Patterns

### 10.1 Pattern: Complete Rule Set Structure

```
FIXED Act IS "Veterans' Entitlements Act 1986"
FIXED minimum distance threshold IS 50
FIXED long distance threshold IS 350

INPUT person served AS BOOLEAN
INPUT distance to treatment AS NUMBER
INPUT form of transport AS LIST
    ITEM car
    ITEM train
    ITEM plane

# Reference: https://legislation.gov.au/xxx
# Section: Section 1 - Eligibility
# Original: A person is eligible if the person is a veteran and has completed the qualifying period
eligible person
    AND member of the Defence Force
    AND completed the basic service period

# Reference: https://legislation.gov.au/xxx
# Section: Section 2 - Allowance
# Original: Allowance is 100 if distance > 50
allowance amount IS CALC (distance > minimum distance threshold ? 100 : 50)
    NEEDS distance
```

### 10.2 Anti-Pattern: Using IF...THEN...ELSE

```
# WRONG:
IF distance > 50 THEN allowance = 100 ELSE allowance = 50

# CORRECT:
allowance amount IS CALC (distance > minimum distance threshold ? 100 : 50)
    NEEDS distance
```

### 10.3 Anti-Pattern: Inline Lists

```
# WRONG:
AND service type IS IN LIST: [warlike, non-warlike, peacekeeping]

# CORRECT:
FIXED qualifying service type AS LIST
    ITEM warlike service
    ITEM non-warlike service
    ITEM peacekeeping service

AND service type IS IN LIST: qualifying service type
```

### 10.4 Anti-Pattern: Mixing AND/OR at Same Level

```
# WRONG -- ambiguous:
the person qualifies
    AND the person is a veteran
    OR the person is a reservist

# CORRECT -- with virtual node:
the person qualifies
    OR the person qualifies via veteran status
        AND the person is a veteran
    OR the person qualifies via reservist status
        AND the person is a reservist
```

### 10.5 Anti-Pattern: snake_case Variable Names

```
# WRONG:
person_is_eligible
    AND has_completed_service

# CORRECT:
eligible person
    AND completed the basic service period
```

### 10.6 Anti-Pattern: IS CALC Inside a Child Dependency

```
# WRONG:
the total amount
    AND the subtotal IS CALC (amount * rate)
        NEEDS amount
        NEEDS rate

# CORRECT:
the subtotal IS CALC (amount * rate)
    NEEDS amount
    NEEDS rate

the total amount
    AND the subtotal
```

### 10.7 Anti-Pattern: IS TRUE / IS FALSE as Child Rules

```
# WRONG:
Dean is a man
    AND Dean has a wife IS TRUE
    AND Dean is a kind man IS TRUE

# CORRECT:
Dean is a man
    AND Dean has a wife = TRUE
    AND Dean is a kind man = TRUE
```

### 10.8 Pattern: Date Logic (Modelled Externally)

Date arithmetic is NOT supported in INFERRA. Model date logic externally and pass results as INPUTs:

```
# Instead of computing age from date of birth in the rule:
# INPUT date of birth AS DATE
# age IS CALC (today's date - date of birth)     <-- NOT SUPPORTED

# Pass precomputed values as INPUTs:
INPUT the person's age AS NUMBER
INPUT the claim due date AS DATE
```

---

## 11. Quick Reference Card

### Declaration Keywords

| Keyword | Purpose | Example |
|---------|---------|---------|
| FIXED | Declare a constant | `FIXED threshold IS 50` |
| INPUT | Declare a user-provided variable | `INPUT distance AS NUMBER` |
| AS | Specify data type | `INPUT name AS TEXT` |
| IS | Assign value (in declarations) | `FIXED rate IS 31.35` |
| ITEM | Define a list option | `ITEM warlike service` |

### Dependency Type Keywords

| Keyword | Meaning | Convergence Impact |
|---------|---------|-------------------|
| AND | All must be true | All must be answered |
| OR | Any one must be true | At least one must be answered |
| NOT | Inverts the child result | No change |
| KNOWN | Checks if value exists | No change |
| MANDATORY | Must ask and must answer | CANNOT converge without answer |
| OPTIONALLY | Ask but answer optional | CAN converge without answer |
| POSSIBLY | May or may not ask | CAN converge without answer |

### Rule Type Keywords

| Keyword | Purpose | Example |
|---------|---------|---------|
| IS | Value conclusion | `A IS B` |
| IS TRUE | Boolean true | `A IS TRUE` |
| IS FALSE | Boolean false | `A IS FALSE` |
| IS CALC | Expression/calculation | `A IS CALC (B * C)` |
| IS IN LIST | List membership | `A IS IN LIST: B` |
| = > < >= <= | Comparison | `A > 50` |
| ? : | Ternary (if/else) | `A > B ? X : Y` |
| NEEDS | Required expression input | `NEEDS distance` |
| WANTS | Optional expression input | `WANTS the height` |

### Iteration Keywords

| Keyword | Purpose | Example |
|---------|---------|---------|
| ITERATE: LIST OF | Loop over list | `ALL service ITERATE: LIST OF service history` |
| ALL | Every item must pass | `ALL service ITERATE: ...` |
| NONE | No item must pass | `NONE service ITERATE: ...` |
| NOT ALL | At least one must fail | `NOT ALL service ITERATE: ...` |
| N (number) | At least N must pass | `3 service ITERATE: ...` |

### Structural Conventions

| Convention | Rule |
|-----------|------|
| Indentation | 4 spaces per level |
| Comments | `# Reference:`, `# Section:`, `# Original:` before every rule block |
| Naming | Use exact legislative phrasing with spaces (never snake_case) |
| Virtual Nodes | Create explicitly when mixing AND/OR at same level |
| Literals | Double-quoted strings (e.g., `"MALE"`) |
| Variables | Unquoted names reference other variables (e.g., `another person's last name`) |
| Order | FIXED first, then INPUT, then rule blocks |

You are an expert NADIA rule engineer. Your task is to transform any given Australian legislative or policy document into a fully compliant NADIA rule set (Version 0.2), strictly adhering to the syntax and structure defined in the official NADIA guidance.

CRITICAL SYNTAX RULES (MUST BE FOLLOWED):

1. FIXED and INPUT declarations come first.
   - FIXED: Used for static constants (e.g., rates, dates, definitions).
   - INPUT: Declare all user-provided or runtime variables with explicit data types (BOOLEAN, NUMBER, DATE, TEXT, LIST).
   - For LIST inputs, define each ITEM on a new line, indented with 4 spaces.
   - NEVER use snake_case (e.g., person_is_eligible). Use spaces and exact legislative phrasing (e.g., eligible person).

2. Every rule block MUST be preceded by three comment lines:
   # Reference: [URL or doc reference]
   # Section: [Section title or number]
   # Original: [Exact legislative text being modeled]

3. Rule Types and Structure:
   - Use 4-space indentation for child rules.
   - NEVER mix AND/OR with NEEDS/WANTS in the same rule block.
   - NEEDS and WANTS can ONLY appear under an Expression Conclusion Line (IS CALC).
   - NEVER use IF...THEN...ELSE — replace with ternary operator (? :) inside IS CALC or with OR/AND branching.
   - NEVER use IS CALC inside a child dependency — IS CALC must be the top-level statement of an Expression Conclusion Line.
   - For Value Conclusion Lines (X IS TRUE, X IS "value"), do NOT add child rules unless logically necessary. Plain statements like "part 2 creates no enforceable rights IS TRUE" are valid and correct.
   - For Comparison Conclusion Lines (A = B, A > 5), the engine will automatically prompt for missing values — do NOT add NEEDS.
   - Avoid mixing AND and OR at the same level — if needed, the engine will auto-create a virtual node, but prefer helper rules for clarity.

4. Virtual Node Handling (CRITICAL):
   - If a rule has multiple OR/AND branches at the same indentation level, and there is no clear parent grouping, you MUST create a virtual node to ensure correct logical evaluation.
   - Virtual nodes are not visible in the source law — they are structural aids for the engine.
   - Example:
        meals only reimbursement
            OR meals required AND number of nights = 0 AND distance to treatment > minimum distance threshold AND distance to treatment <= long distance threshold
                AND meals only reimbursement = meals short distance rate
     → This is ambiguous. Rewrite as:
        meals only reimbursement
            OR meals required virtual one
                AND meals required
                AND number of nights = 0
                AND distance to treatment > minimum distance threshold
                AND distance to treatment <= long distance threshold
                AND meals only reimbursement = meals short distance rate
            OR meals condition not met
                AND meals only reimbursement = 0
   - Always create a virtual node when multiple conditions are chained at the same level under OR/AND without grouping.
   - Name virtual nodes descriptively: e.g., “attendant scenario one”, “distance condition met”, “meals required virtual one”.

5. Expression Handling:
   - Use IS CALC for all arithmetic, date math (if precomputed externally), or conditional expressions.
   - Use ternary operator: condition ? value_if_true : value_if_false
   - Date arithmetic is NOT supported in NADIA — model date logic externally and pass results as INPUTs (e.g., “claim due date”).
   - ROUND, MAX, MIN are supported.
   - All variables used in an IS CALC expression must be declared with NEEDS (if mandatory) or WANTS (if optional).

6. Logical Branching:
   - Use OR/AND for mutually exclusive or cumulative conditions.
   - Use KNOWN for checking if a value has been provided.
   - Use NOT for negation.
   - Use IS IN LIST: [list name] for membership checks.
   - NEVER use inline lists like [item1, item2]. Instead:
        FIXED valid_purposes AS LIST
            ITEM buy land and build house on land
            ITEM build house on land already owned
        ...
        AND loan purpose IS IN LIST: valid_purposes

7. Naming Conventions:
   - NEVER use snake_case (e.g., person_is_eligible).
   - ALWAYS use the exact terminology from the legislation, with spaces (e.g., eligible person, completed the basic service period).
   - Do not reword or abbreviate legislative terms.

8. Final Output:
   - Output ONLY plain text — no markdown, no code blocks, no explanations.
   - Start with FIXED declarations, then INPUT declarations, then rule blocks in logical order.
   - Ensure every legislative provision is modeled — do not omit any meaning.

EXAMPLE STRUCTURE:

FIXED Act IS "Example Act 2025"
FIXED threshold IS 50

INPUT person served AS BOOLEAN
INPUT distance AS NUMBER
INPUT form of transport AS LIST
    ITEM car
    ITEM train

# Reference: https://example.gov.au/doc123
# Section: Section 1 - Definitions
# Original: veteran means a person who has served...
eligible person
    AND member of the Defence Force
    AND completed the basic service period

# Reference: https://example.gov.au/doc123
# Section: Section 2 - Allowance
# Original: Allowance is $100 if distance > 50...
allowance amount IS CALC (
    distance > threshold ? 100 : 50
    )
    NEEDS distance

Transform the provided document into a complete, production-ready NADIA rule set following the above rules exactly.

-------------------- Start of NADIA rule syntax details -----------------------------

# ============== NADIA RULE SYNTAX (FROM OFFICIAL PDF) ==============
the below guide text is written in markdown# NADIA Inference Engine    Version 0.2

## NADIA RULE Dictionary for each case

### FIXED
[FIXED](FIXED keyword) [the gender is accepted](variable name) [IS](IS keyword) [FALSE](value)  
- Note: this ‘variable name’ is used as a ‘Key’ for `Map<String, FactValue>` / `Dictionary<String, FactValue>` / `dict` FactMap
---

### INPUT
[INPUT](INPUT keyword) [the boy’s name](variable name) [AS](AS keyword) [TEXT](TEXT keyword and it_is_data_type) [IS](IS keyword) [MALE](value)  
[INPUT](INPUT keyword) [the boy’s DoB](variable name) [AS](AS keyword) [DATE](DATE keyword and it_is_data_type)  
[INPUT](INPUT keyword) [the boy’s gender](variable name) [AS](AS keyword) [TEXT](TEXT keyword and it_is_data_type) [IS](IS keyword) [MALE](value)  
[INPUT](INPUT keyword) [the boy’s gender](variable name) [AS](AS keyword) [LIST](LIST keyword and it_is_data_type) [AS](AS keyword) [LIST](LIST keyword and it_is_data_type)  
&emsp;[ITEM](ITEM keyword this keyword is for item for LIST data type) [MALE](value for ITEM)  
&emsp;[ITEM](ITEM keyword this keyword is for item for LIST data type) [FEMALE](value for ITEM)  
[INPUT](INPUT keyword) [the fruit that the client had](variable name) [AS](AS keyword) [LIST](LIST keyword and it_is_data_type)  
&emsp;[ITEM](ITEM keyword this keyword is for item for LIST data type) [apple](value for ITEM)  
&emsp;[ITEM](ITEM keyword this keyword is for item for LIST data type) [pear](value for ITEM)  
&emsp;[ITEM](ITEM keyword this keyword is for item for LIST data type) [grapes](value for ITEM)  

- **Note**: values (*can be various types*)  
- **Note**: If a string line contains the keyword `LIST`, then the lines below will be treated as `ITEM` entries **unless** the line is not indented.  
- **Note**: `ITEM` is not going to be an Object. The value of `ITEM` is stored directly in an Object.

---

### RULE
[[the person’s drinking habit](variable name) [IS](IS keyword) [frequent drinker](value)](rule name)  
&emsp;[AND](AND keyword dependency type) [[number of drinks the person consumes a week](variable name) [>](operator) [3](value)](rule name)  
&emsp;[AND](AND keyword dependency type) [[number of drinks the person consumes a week](variable name) [<](operator) [7](value)](rule name)  
- Note: this ‘rule name’ is used as a ‘Key’ for `Map<String, Node>` / `Dictionary<String, Node>` / `dict` NodeMap

[Do we know the boy’s identity](variable name and rule name)  
&emsp;[AND KNOWN](AND KNOWN keyword dependency type, dependency type with known type) [the boy’s name](variable name and rule name)  
&emsp;[AND KNOWN](AND KNOWN keyword dependency type, dependency type with known type) [the boy’s dob](variable name and rule name)  
&emsp;[OR](OR keyword dependency type) [we have the boy’s passport](variable name and rule name)  
- Note: this ‘rule name’ is used as a ‘Key’ for `Map<String, Node>` / `Dictionary<String, Node>` / `dict` NodeMap

[the person made it to Las Vegas](variable name and rule name)  
&emsp;[AND NOT](AND NOT keyword dependency type, dependency type with negation) [the person missed the flight](variable name and rule name)  
- Note: Negation and/or Known are part of Dependency type. If the same ‘rule name’ is used in different places, those rules refer to the **same rule**.

[the person did cross the street](variable name and rule name)  
&emsp;[AND NOT](AND NOT keyword dependency type, dependency type with negation) [the street was busy](variable name and rule name)  
&emsp;[AND MANDATORY](AND MANDATORY keyword dependency type, dependency type with mandatory) [the person is able to walk](variable name and rule name)  

[the client qualifies for the grant](variable name and rule name)  
&emsp;[OR](OR keyword dependency type) [the client needs the grant](variable name and rule name)  
&emsp;[OR MANDATORY](OR MANDATORY keyword dependency type, dependency type with mandatory) [the client is an adult](variable name and rule name)  

[the person’s first name](variable name) [IS](IS keyword) [MALE](value)  
&emsp;[AND](AND keyword dependency type) [[the person’s first name](variable name) [IS IN LIST](IS IN LIST keyword for checking list) [:](separator) [Male first name list](list name)](rule name)  

[[the rectangle area](variable name) [IS CALC](IS CALC keyword for ExpressionConclusionLine type) [(the rectangle height*the rectangle width)](value/equation)](rule name)  
&emsp;[NEEDS](NEEDS dependency type same as AND MANDATORY) [the rectangle height](variable name and rule name)  
&emsp;[NEEDS](NEEDS dependency type same as AND MANDATORY) [the rectangle width](variable name and rule name)  

[[the rectangle area](variable name) [IS CALC](IS CALC keyword for ExpressionConclusionLine type) [(the height?(the height*the width:the width*the width)](value/equation)](rule name)  
&emsp;[WANTS](WANTS dependency type same as OR) [the height](variable name and rule name)  
&emsp;[NEEDS](NEEDS dependency type same as AND MANDATORY) [the width](variable name and rule name)  
- **Note**: this 'WANTS' dependency type is same as 'OR' dependency type, and 'NEEDS' dependency type is same as 'AND' dependency type

[the person is a son of another person](variable name and rule name)  
&emsp;[AND](AND keyword dependency type) [the person’s first name](variable name) [=](operator) ["MALE"](literal value)  
&emsp;[AND](AND keyword dependency type) [the person’s last name](variable name) [=](operator) [another person’s last name](variable name)  
&emsp;[AND NOT](AND NOT keyword dependency type, dependency type with negation) [the person](variable name) [=](operator) [another person](variable name)  

- **Note**: If a value string is in double quotation marks (e.g., `"MALE"`), it compares a variable’s value with a **literal**.  
  If not in quotes (e.g., `another person’s last name`), it compares two variable values. For instance, if a variable name is `person's first name` and its value is `John`, and value string is `"Tony"` then comparing like `"John"` = `"Tony"`. Another example is that a variable name `person's first name` and its value is `John`, and value string is `another person's first name` and its value is `"Eric"` then it is comparison between `"John"` = `"Eric"`.

[NOT ALL service](dependency type with negation) [ITERATE: LIST OF](ITERATE keyword for IterateLine type) [service history](list name)  
&emsp;[OR](OR keyword dependency type) [one](rule name)  
&emsp;&emsp;[AND](AND keyword dependency type) [enlistment date](variable name) [>=](operator) [01/07/1951](value)  
&emsp;&emsp;[AND](AND keyword dependency type) [discharge date](variable name) [<=](operator) [06/12/1972](value)  
&emsp;&emsp;[AND NOT](AND NOT keyword dependency type, dependency type with negation) [service type](variable name) [IS IN LIST](IS IN LIST keyword for checking list) [:](separator) [Operational service type](list name)  
&emsp;[OR](OR keyword dependency type) [two](rule name)  
&emsp;&emsp;[AND](AND keyword dependency type) [enlistment date](variable name) [>=](operator) [07/04/1994](value)  
&emsp;&emsp;[AND NOT](AND NOT keyword dependency type, dependency type with negation) [service type](variable name) [IS IN LIST](IS IN LIST keyword for checking list) [:](separator) [Operational service type](list name)  

- **Note**: The `ITERATE: LIST OF` rule iterates over each item in the list (e.g., `service history`) and checks if **none** meet the conditions (due to `NOT ALL`).  
- **Note**: Child rules of an `ITERATE` line must be defined **immediately below** it.

---
## NADIA RULE Dictionary for each key words of Fixed, Input, and Rule
### FIXED
FIXED the gender is accepted IS FALSE  
FIXED the gender is accepted IS 1 / 1/ 1988  

### INPUT
INPUT the boy's name AS TEXT  
INPUT the boy's DoB AS DATE  
INPUT the boy's gender AS TEXT IS MALE  
INPUT the boy's gender AS LIST IS MALE  
&emsp;&emsp;ITEM MALE  
&emsp;&emsp;ITEM FEMALE  
INPUT the fruit that the client had AS LIST  
&emsp;&emsp;ITEM apple  
&emsp;&emsp;ITEM pear  
&emsp;&emsp;ITEM grapes  

### RULE
Do we know the boy’s identity  
&emsp;&emsp;AND KNOWN the boy’s name  
&emsp;&emsp;AND KNOWN the boy’s dob  
&emsp;&emsp;OR we have the boy’s passport  

the person made it to Las Vegas  
&emsp;&emsp;AND NOT the person missed the flight  

the person did cross the street  
&emsp;&emsp;AND NOT the street was busy  
&emsp;&emsp;AND MANDATORY the person is able to walk  

the client qualifies for the grant
&emsp;&emsp;OR the client needs the grant  
&emsp;&emsp;OR MANDATORY the client is an adult  

the client qualifies for the first grant  
the client qualifies for the second grant  
the client qualifies for the third grant  
[the person’s drinking habit IS frequent drinker](1) 
&emsp;&emsp;AND number of drinks the person consumes a week > 3  
&emsp;&emsp;AND number of drinks the person consumes a week < 7  
the person is a son of another person  
&emsp;&emsp;[AND the person’s first name = MALE](2)  
&emsp;&emsp;AND the person's last name = another person’s last name  
&emsp;&emsp;AND NOT the person = another person  
[the person’s first name IS MALE](2)  
&emsp;&emsp;AND the person's first name IS IN LIST  
the rectangle area IS CALC (the rectangle height * the rectangle width)  
&emsp;&emsp;NEEDS the rectangle height  
&emsp;&emsp;NEEDS the rectangle width  
the another rectangle area IS CALC ( the height ? (the height * the width : the width * the width) )  
&emsp;&emsp;WANTS the height  
&emsp;&emsp;NEEDS the width  
the person is eligible for a service  
&emsp;&emsp;[AND the person’s drinking habit = frequent drinker](1)  
&emsp;&emsp;[AND the person’s first name = MALE](2)  
&emsp;&emsp;AND KNOWN the rectangle area  

- **Note**: same labelled reference indicates that it is a same rule but in different format
---

## Rule Types

### 1. Value Conclusion Line
- **Examples**:  
  - `A IS B`  
  - `A IS FALSE`  
  - `A IS TRUE`  
  - `A IS IN LIST: B`  
- During `selfEvaluation()`, checks if the variable's value matches the given value or is `TRUE`/`FALSE`.
- If the Rule is a child rule then it can be negated or known type with keywords ‘NOT’ and/or ‘KNOWN’. This rule type CANNOT be negated or known type as a parent. In addition, negation and known type will be automatically taken care of when selfEvaluation() is invoked  

- **Note**: this rule type should NOT be a base child rule other than a case of plain statement because a child rule only will be determined by either asking questions to a user or checking working memory.  
E.g)  
[Dean is a man]('A':plain statement)  
&emsp;&emsp;AND [Dean has a wife IS TRUE]('A' IS 'B')  
&emsp;&emsp;AND [Dean is a kind man IS TRUE]('A' IS 'B')  
&emsp;&emsp;AND [Dean was born as a man]('A':plain statement)  
- **The above lines should be written as below;**  
Dean is a man  
&emsp;&emsp;AND [Dean has a wife = TRUE]('A'='B':Comparison type)  
&emsp;&emsp;AND [Dean is a kind man = TRUE]('A' = 'B':Comparison type)  
&emsp;&emsp;AND Dean was born as a man  

--- 

### 2. Comparison Conclusion Line
- **Examples**:  
  - `A = B`  
  - `A > B`  
  - `A < B`  

- Compares two values (literal or variable).
- If a value is missing, asks the user.
- Result stored in working memory.
- Only valid as a **child rule**.

E.g.)  
[Dean = man]('A'='B':Comparison type)  
&emsp;&emsp;[AND Dean has a wife IS TRUE]('A' IS 'B')  
&emsp;&emsp;[AND Dean is a kind man IS TRUE]('A' IS 'B')  
&emsp;&emsp;[AND Dean was born as a man]('A': plain statement)  
- **The above lines should be written as below;**  
[Dean IS man]('A' IS 'B':Value conclusion type)  
&emsp;&emsp;[AND Dean has a wife = TRUE]('A'='B':Comparison type)  
&emsp;&emsp;[AND Dean is a kind man = TRUE]('A'='B':Comparison type)  
&emsp;&emsp;AND Dean was born as a man  

---  

### 3. Expression Conclusion Line
- **Examples**:  
  - `Statement A IS CALC (B * C)`  
    &emsp;&emsp;`NEEDS B`  
    &emsp;&emsp;`NEEDS C`  
  - `Statement A IS CALC (D ? C*D : C*C)`  
    &emsp;&emsp;`WANTS D`  
    &emsp;&emsp;`NEEDS C`  
- Evaluates expressions in parentheses.
- Supports conditional expressions (`?:`).
- Can be parent or child.

- **Note**: Expression Conclusion type rule can be a parent or a child in the rule format
E.g.)
Dean is a man  
&emsp;&emsp;AND Dean's age IS CALC (today's date - Dean's dob)  
&emsp;&emsp;&emsp;&emsp;NEEDS Dean’s dob  
&emsp;&emsp;AND Dean has a wife = TRUE  
&emsp;&emsp;AND Dean is a kind man = TRUE  
&emsp;&emsp;AND Dean was born as a man  

- **The above lines should be written as below;**  
Dean is a man  
&emsp;&emsp;AND Dean's age > 18  
&emsp;&emsp;AND Dean has a wife = TRUE  
&emsp;&emsp;AND Dean is a kind man = TRUE  
&emsp;&emsp;AND Dean was born as a man  
Dean's age IS CALC (today's date - Dean's dob)  
&emsp;&emsp;NEEDS Dean's dob  

---

### 4. Iterate Line
- **Example**:  
  - `ALL service ITERATE: LIST OF service history`  
  &emsp;&emsp;`OR one`  
  &emsp;&emsp;&emsp;&emsp;`AND enlistment date >= 01/07/1951`  
  &emsp;&emsp;&emsp;&emsp;`AND discharge date <= 06/12/1972`  
- Iterates over a list and evaluates conditions for each item.
- Child rules must follow immediately.
- Only valid as a **child rule**.

ALL service ITERATE: LIST OF service history  
&emsp;&emsp;AND number of services  
&emsp;&emsp;AND iterate rules  
&emsp;&emsp;&emsp;&emsp;OR one  
&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;AND enlistment date >= 01/07/1951  
&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;AND discharge date <= 6/12/1972  
&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;AND NOT service type IS IN LIST: Special service  
&emsp;&emsp;&emsp;&emsp;OR two  

two  
&emsp;&emsp;AND enlistment date >= 22/05/1986  
&emsp;&emsp;AND yearly period of service by 6/04/1994 >= 3  

- **The above lines should be written as below;**  
person must meet military service criteria  
&emsp;&emsp;AND NOT ALL service ITERATE: LIST OF service history  
&emsp;&emsp;AND number of services  
&emsp;&emsp;AND iterate rules  
&emsp;&emsp;&emsp;&emsp;OR one  
&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;AND enlistment date >= 01/07/1951  
&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;AND discharge date <= 6/12/1972  
&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;AND NOT service type IS IN LIST: Special service  
&emsp;&emsp;&emsp;&emsp;OR two  
&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;AND enlistment date >= 22/05/1986  
&emsp;&emsp;&emsp;&emsp;AND yearly period of service by 6/04/1994 >= 3  

---

### 5. Virtual Line
- Automatically created when a parent rule has both `AND` and `OR` dependencies.
- Invisible to users.
- Ensures correct logical grouping.
- Example:  
  ```text
  person must meet military service criteria  
    AND number of services
    OR one  
      AND enlistment date >= 01/07/1951
      AND discharge date <= 6/12/1972
      AND NOT service type IS IN LIST: Special service
    OR two

- **Above case will create below rule structure in NADIA engine**
  ```text  
  person must meet military service criteria  
      OR VirtualNode — person must meet military service criteria  
        AND number of services
      OR one
        AND enlistment date >= 01/07/1951
        AND discharge date <= 6/12/1972
        AND NOT service type IS IN LIST: Special service
      OR two
  ```
---  

## Rule Type Matrix

The following table describes the characteristics of each rule type in the NADIA Inference Engine.  
It distinguishes between behavior in the **Rule Format** (as written in rule files) and **Rule Structure** (as represented internally in the engine).

| Rule Type               | Option / Keyword           | In Rule Format (File) | In Rule Structure (Engine) | Can Be Child | Can Be Parent | Needs Self-Evaluation |
|-------------------------|----------------------------|------------------------|-----------------------------|--------------|---------------|------------------------|
| **Value Conclusion**    | No Keywords                | ✅                     | ✅                          | ✅           | ✅            | Only if not plain      |
|                         | `NOT`                      | ✅                     | ✅                          | ✅           | ❌            | ✅                     |
|                         | `KNOWN`                    | ✅                     | ✅                          | ✅           | ❌            | ✅                     |
|                         | `MANDATORY`, `OPTIONALLY`, `POSSIBLY` | ✅              | ✅                          | ✅           | ✅            | ❌                     |
|                         | `MANDATORY NOT`, `POSSIBLY NOT` | ✅              | ✅                          | ✅           | ❌            | ✅                     |
|                         | `MANDATORY KNOWN`, `POSSIBLY KNOWN` | ✅            | ✅                          | ✅           | ❌            | ✅                     |
|                         | `MANDATORY NOT KNOWN`, `POSSIBLY NOT KNOWN` | ✅      | ✅                          | ✅           | ❌            | ✅                     |
| **Comparison**          | No Keywords                | ✅                     | ✅                          | ✅           | ❌            | ✅                     |
|                         | `NOT`                      | ✅                     | ✅                          | ✅           | ✅            | ✅                     |
|                         | `KNOWN`                    | ❌                     | ❌                          | ❌           | ❌            | ❌                     |
|                         | `MANDATORY`, `OPTIONALLY`, `POSSIBLY` | ✅          | ✅                          | ✅           | ❌            | ❌                     |
|                         | `MANDATORY NOT`, `POSSIBLY NOT` | ✅          | ✅                          | ✅           | ❌            | ✅                     |
|                         | Others                     | ❌                     | ❌                          | ❌           | ❌            | ❌                     |
| **Expression**          | No Keywords                | ✅                     | ✅                          | ✅           | ✅            | ✅                     |
|                         | `NOT`                      | ✅                     | ✅                          | ✅           | ❌            | ✅                     |
|                         | `KNOWN`                    | ❌                     | ❌                          | ❌           | ❌            | ❌                     |
|                         | `NEEDS` (≡ `MANDATORY`)    | ✅                     | ✅                          | ✅           | ❌            | ❌                     |
|                         | `WANTS` (≡ `OR`)           | ✅                     | ✅                          | ✅           | ❌            | ❌                     |
|                         | Others                     | ❌                     | ❌                          | ❌           | ❌            | ❌                     |
| **Iterate**             | `ALL`, `NONE`, or number   | ✅                     | ✅                          | ✅           | ❌            | ✅                     |
|                         | `NOT`                      | ✅                     | ✅                          | ✅           | ❌            | ✅                     |
|                         | `KNOWN`                    | ❌                     | ❌                          | ❌           | ❌            | ❌                     |
|                         | `MANDATORY`, `OPTIONALLY`, `POSSIBLY` | ✅      | ✅                          | ✅           | ❌            | ❌                     |
|                         | Others                     | ❌                     | ❌                          | ❌           | ❌            | ❌                     |
| **Virtual**             | Auto-generated             | ❌ (not visible)       | ✅                          | ❌           | ✅            | ✅                     |

> **Note**:  
> - A **Virtual Rule** is automatically created by the engine when a parent rule has both `AND` and `OR` child dependencies.  
> - `NEEDS` ≡ `AND MANDATORY`, `WANTS` ≡ `OR`.  
> - Rules with `KNOWN` or `NOT` can only appear as **child rules**, not as parents.  
> - Plain statements (e.g., `Dean is a man`) are treated as `Value Conclusion` rules with no evaluation needed.

-------------------- End of NADIA rule syntax details ---------------------------

Follow the NADIA rule engine specification provided at the top of this context — it defines:
- Keywords: MANDATORY, OPTIONALLY, NOT, KNOWN, IS IN LIST
- Structure: indentation, references, INPUT/FIXED declarations
- Logic decomposition: how to handle OR/AND groups
- Reference formatting

Based on the legislation and policy documents below, generate a complete NADIA rule set for:
- Income support eligibility
- Service type definitions (warlike, non-warlike, peacekeeping, hazardous)
- Residency, discharge, enlistment conditions
- All fixed values and inputs 

You are an expert rule translator for the NADIA Inference Engine (Version 0.2). Your task is to generate a complete set of NADIA-compliant rules for Australian DVA income support eligibility under the Military Rehabilitation and Compensation Act 2004 (MRCA), strictly following the syntax and structure defined in the `nadia_guidance_CLEAN.md` specification.

Follow these rules exactly:

1. Output only plain text — no markdown, no code blocks, no explanations.
2. Start with all `FIXED` and `INPUT` declarations.
3. Use 4-space indentation for child rules.
4. Every rule block must be preceded by:
   # Reference: <URL>
   # Section: <section name or number>
   # Original: <exact quoted text from legislation or policy>
5. Use `MANDATORY`, `OPTIONALLY`, `KNOWN`, `NOT`, `AND`, `OR` only as dependency types.
6. For expressions, use `IS CALC` with `NEEDS` or `WANTS`.
7. For list membership, use `IS IN LIST: <list name>`.
8. For iteration, use `NOT ALL service ITERATE: LIST OF service history` with indented `OR`/`AND` sub-rules.
9. Define all variables and lists before use.
10. Do not omit any rules or meanings from the source legislation.


Now generate the full NADIA rule set as plain text, starting with `FIXED` and `INPUT`, then all `RULE` blocks. Ensure all logic is decomposed, all dependencies are correct, and all references are included.

Requirements:
- Start with FIXED and INPUT declarations
- Every rule block must be preceded by # Reference, # Section, # Original
- Break compound logic into OR/AND blocks
- Define all key terms
- Use proper 4-space indentation
- Output only plain text — no markdown or explanations


Now generate the full NADIA-compliant rule set:

# INFERRA-PyRest FastAPI Conversion Plan

## Current State Summary

**Migration Complete!** The project has been fully migrated from Flask to FastAPI.

- FastAPI application entrypoint at `src/main.py`.
- Clean `src/` package structure with domain, adapters, ports, and shared modules.
- FastAPI routers for rules, inference, and files endpoints.
- Session management with `InferenceSession`, `SessionStorePort`, and `InMemorySessionStore`.
- Pydantic schemas for all API requests/responses.
- File conversion endpoint with streaming support.
- 47 tests passing for services and session store.
- Legacy Flask code removed.
- Single `pyproject.toml` for dependency management.

### Completed Steps

| Step | Description | Status |
|------|-------------|--------|
| 1 | Create FastAPI application entrypoint | ✅ Done |
| 2 | Build inbound HTTP structure | ✅ Done |
| 3 | Port stateless rule endpoints | ✅ Done |
| 4 | Introduce request/response schemas | ✅ Done |
| 5 | Extract service logic from `app.py` | ✅ Done |
| 6 | Redesign inference state management | ✅ Done |
| 7 | Port inference endpoints | ✅ Done |
| 8 | Port file conversion endpoint | ✅ Done |
| 9 | Add migration-safe tests | ✅ Done |
| 10 | Remove duplicate legacy code | ✅ Done |

## Goal

Complete the migration from Flask to FastAPI in a controlled order, while preserving existing behavior and reducing risk from the duplicated code paths.

## Working Agreement

- We will implement the steps in order.
- Before each implementation step, I will stop and ask for your approval.
- If a step is ambiguous or risky, I will ask for clarification before changing code.

## Step-by-Step Plan

### Step 1. Create the FastAPI application entrypoint

Create the new FastAPI app foundation, likely under `src/main.py` or an equivalent inbound HTTP entrypoint.

Scope:

- Define the `FastAPI()` application object.
- Add configuration loading from `src.config`.
- Add router registration structure.
- Add baseline exception handling and app startup shape.
- Add CORS or middleware only if the current frontend/API usage requires it.

Expected outcome:

- The project has a real FastAPI application object that can be started with `uvicorn`.
- The app exists alongside Flask temporarily while the migration proceeds.

Clarifications to confirm before implementation:

- Preferred FastAPI entrypoint path.
- Whether CORS should be enabled immediately.
- Whether we should keep `app.py` runnable during the transition.

### Step 2. Build the inbound HTTP structure

Create the FastAPI inbound layer under `src/adapters/inbound`.

Scope:

- Add API package structure for routers.
- Split endpoints by domain area, for example `rules`, `inference`, and `files`.
- Add dependency injection helpers such as database session access.

Expected outcome:

- The FastAPI app has a maintainable router layout instead of one large monolithic file.

Clarifications to confirm before implementation:

- Preferred router grouping and URL layout.

### Step 3. Port the stateless rule endpoints first

Move the lower-risk rule APIs from Flask to FastAPI before touching inference state.

Candidate endpoints from `app.py`:

- `searchRuleByName`
- `findRuleTreeDataByName`
- `findRuleTextByName`
- `findAllRules`
- `updateRule`
- `createNewRule`
- `saveConvertedRule`
- `createFile`
- `targetNodeNameList`

Scope:

- Recreate these endpoints as FastAPI routes.
- Replace manual JSON validation with FastAPI request parsing where possible.
- Use the new repository and adapter layers instead of direct legacy imports where available.

Expected outcome:

- The easiest endpoints are moved first and begin exercising the new app structure.

Clarifications to confirm before implementation:

- Whether endpoint paths must remain exactly the same for frontend compatibility.

### Step 4. Introduce request and response schemas

Add Pydantic models for API inputs and outputs.

Scope:

- Create typed request models for rule create/update, file save, and inference payloads.
- Create consistent error response shapes where appropriate.
- Remove route-local field extraction and ad hoc validation where FastAPI can handle it.

Expected outcome:

- API contracts become explicit and easier to validate and test.

Clarifications to confirm before implementation:

- Whether strict backward-compatible response shapes are required, including key names and string formatting.

### Step 5. Extract reusable application/service logic from `app.py`

Move non-HTTP logic out of route functions.

Scope:

- Extract rule parsing helpers.
- Extract rule loading and decoding helpers.
- Extract inference engine setup/reset logic.
- Separate orchestration logic from request/response handling.

Expected outcome:

- Routes stay thin and most behavior becomes reusable and testable.

Clarifications to confirm before implementation:

- Preferred home for service-level orchestration code.

### Step 6. Redesign inference state management ✅ COMPLETED

Replace the current stateful behavior that relies on a `requests.session()` object in `app.py`.

Why this matters:

- The current Flask-era session pattern is not an appropriate FastAPI state model.
- This is the highest-risk part of the migration.

**Implementation Summary:**

1. **Created `InferenceSession` dataclass** (`src/domain/inference/session.py`)
   - Holds inference engine, assessment, and metadata
   - Tracks created_at and last_accessed timestamps

2. **Created `SessionStorePort` interface** (`src/ports/session_store_port.py`)
   - Abstract interface for session storage
   - Methods: get, save, delete, exists, list_sessions, clear_expired, clear_all

3. **Implemented `InMemorySessionStore`** (`src/adapters/outbound/session/in_memory_session_store.py`)
   - Thread-safe with RLock
   - TTL-based expiration support
   - Can be swapped for Redis later

4. **Created `InferenceSessionService`** (`src/domain/inference/session_service.py`)
   - Generates unique session IDs (UUID)
   - Creates and manages inference sessions
   - Replaces Flask session-based approach

5. **Added dependency injection** (`src/dependencies.py`)
   - Singleton session store
   - Request-scoped repositories
   - Helper for testing (reset_singletons)

6. **Added tests** (`tests/adapters/outbound/session/test_in_memory_session_store.py`)
   - 10 tests covering all session store operations

**Key Design Decisions:**
- Session ID is now explicit (UUID) rather than implicit (target_node_name)
- Clients must provide session_id to continue an existing session
- In-memory storage is suitable for single-worker deployments
- Interface allows easy swap to Redis for multi-worker deployments

**Expected outcome:**

- Inference APIs can run correctly under FastAPI without relying on Flask-style global/session behavior.

### Step 7. Port the inference endpoints ✅ COMPLETED

After state handling is agreed and implemented, move the inference APIs.

**Implementation Summary:**

1. **Created Pydantic schemas** (`src/schemas/inference_schemas.py`)
   - `SessionCreateRequest/Response` - for creating inference sessions
   - `NextQuestionResponse`, `FeedAnswerRequest/Response` - for Q&A flow
   - `EditAnswerRequest/Response` - for editing answers
   - `SummaryResponse` - for assessment summary
   - `UpdateHistoryRequest/Response` - for history updates

2. **Updated RuleService** (`src/services/rule_service.py`)
   - Added `history_dict` parameter to `build_rule_set_parser()`
   - Added `get_history_for_ml_inference()` method

3. **Updated InferenceSessionService** (`src/domain/inference/session_service.py`)
   - Added `create_session_from_rule()` method for convenience
   - Integrates with RuleService for rule parsing

4. **Implemented inference router** (`src/adapters/inbound/http/routes/inference.py`)
   - Modernized paths: `/api/v1/inference/...`
   - Modernized responses: snake_case, proper booleans

**Endpoint Mapping:**

| Old Flask Endpoint | New FastAPI Endpoint | Method |
|-------------------|---------------------|--------|
| `/service/inference/setInferenceEngine` | `/api/v1/inference/sessions` | POST |
| `/service/inference/setMachineLearningInferenceEngine` | `/api/v1/inference/sessions/ml` | POST |
| `/service/inference/getNextQuestion` | `/api/v1/inference/next-question` | GET |
| `/service/inference/feedAnswer` | `/api/v1/inference/feed-answer` | POST |
| `/service/inference/editAnswer` | `/api/v1/inference/edit-answer` | POST |
| `/service/inference/viewSummary` | `/api/v1/inference/summary` | GET |
| `/service/rule/updateHistory` | `/api/v1/inference/history` | POST |

**Key Changes:**
- Session ID now explicit (in query/body) instead of implicit
- All endpoints require `session_id` to continue an existing session
- Response format modernized (snake_case, actual booleans)
- ML inference uses historical data to optimize question ordering

**Expected outcome:**

- The interactive inference flow works through FastAPI.

### Step 8. Port the file conversion endpoint ✅ COMPLETED

Migrate the document conversion and streaming flow.

**Implementation Summary:**

1. **Created `FileConversionService`** (`src/services/file_service.py`)
   - `validate_uploaded_file()` - Validates file name, type, size
   - `convert_to_markdown()` - Converts PDF/DOCX/MD to markdown
   - `save_upload_to_temp()` - Saves UploadFile content to temp file
   - `cleanup_temp_file()` - Cleans up temporary files

2. **Created file schemas** (`src/schemas/file_schemas.py`)
   - `ConversionResponse` - Success response model
   - `ConversionError` - Error response model

3. **Implemented files router** (`src/adapters/inbound/http/routes/files.py`)
   - Modernized path: `/api/v1/files/...`
   - Uses FastAPI `UploadFile` for file uploads
   - Uses `StreamingResponse` for streaming output
   - Proper temp file cleanup in finally block

**Endpoint Mapping:**

| Old Flask Endpoint | New FastAPI Endpoint | Method |
|-------------------|---------------------|--------|
| `/service/file/convert` | `/api/v1/files/convert` | POST |
| (new) | `/api/v1/files/convert-to-markdown` | POST |

**Key Features:**
- Supports PDF, DOCX, DOC, MD, MARKDOWN files
- Streams LLM-transformed INFERRA rules as plain text
- Proper file validation before processing
- Temp file cleanup guaranteed even on errors
- New `/convert-to-markdown` endpoint for preview/debug

**Expected outcome:**

- File conversion works through FastAPI with proper streaming behavior.

### Step 9. Add migration-safe tests ✅ COMPLETED

Build a safety net around the new structure before removing the old one.

**Implementation Summary:**

1. **Fixed Python version requirement** (`pyproject.toml`)
   - Lowered `requires-python` from `>=3.11` to `>=3.10` for compatibility

2. **Removed Flask dependencies from FastAPI code**
   - Removed `werkzeug.utils.secure_filename` from `doc_converter.py`
   - Replaced with standard `os.path.basename()` for filename sanitization

3. **Fixed test imports**
   - `test_rule_service.py`: Updated to use `RuleEntity`, `RuleFileEntity` instead of `Rule`, `History`
   - `test_file_service.py`: Updated to use `FileConversionService` instead of `FileService`
   - `test_rule_repository.py`: Updated to use `RuleRepositoryImpl` instead of `RuleRepository`
   - `test_inference_router.py`: Fixed `SessionCreateMLRequest` to `MLSessionCreateRequest`
   - `test_files_router.py`: Fixed `FileService` to `FileConversionService`

4. **Test coverage (47 tests passing)**
   - Session store tests: 10 tests
   - RuleService tests: 16 tests
   - FileConversionService tests: 10 tests
   - InferenceSessionService tests: 11 tests

**Key Design Decisions:**
- Tests use mocks for database and external dependencies
- Router tests remain as integration tests (require more setup)
- Core service logic is well-covered by unit tests

**Expected outcome:**

- The migration becomes easier to verify incrementally.

### Step 10. Remove duplicate legacy paths and Flask dependencies ✅ COMPLETED

Clean up only after FastAPI parity is in place.

**Implementation Summary:**

1. **Deleted legacy Flask files**
   - `app.py` - Legacy Flask application
   - `utils.py` - Legacy utility functions
   - `requirements.txt` - Legacy requirements
   - `Pipfile` and `Pipfile.lock` - Legacy Pipenv files

2. **Removed duplicate modules**
   - `src/constants/` → use `src/shared/constants/`
   - `src/inference/` → use `src/domain/inference/`
   - `src/nodes/` → use `src/domain/nodes/`
   - `src/fact_values/` → use `src/domain/fact_values/`
   - `src/tokens/` → use `src/domain/tokens/`
   - `src/rule_parser/` → use `src/domain/rule_parser/`
   - `src/repository/` → use `src/adapters/outbound/persistence/`
   - `src/routers/` → use `src/adapters/inbound/http/routes/`
   - `src/loggers/` → use `src/shared/loggers/`
   - `src/domain/models/models.py` - Legacy Flask-SQLAlchemy models

3. **Cleaned up other files**
   - Removed `pandoc-3.8-x86_64-macOS.pkg` installer
   - Removed `inferra_pyrest.egg-info/` build artifact
   - Updated `.gitignore` for cleaner ignores

**Final Project Structure:**
```
src/
├── adapters/
│   ├── inbound/http/routes/    # FastAPI routers
│   └── outbound/
│       ├── llm/                 # LLM client
│       ├── persistence/         # SQLAlchemy repository
│       └── session/             # Session store
├── domain/
│   ├── fact_values/
│   ├── inference/               # Inference engine, sessions
│   ├── models/                  # Domain entities
│   ├── nodes/
│   ├── rule_parser/
│   └── tokens/
├── ports/                       # Abstract interfaces
├── schemas/                     # Pydantic models
├── services/                    # Business logic
└── shared/
    ├── constants/
    └── loggers/
```

**Expected outcome:**

- One clean `src.*` import graph remains.
- FastAPI becomes the single supported HTTP framework in the project.

## Implementation Order

1. ~~Create FastAPI application entrypoint.~~ ✅
2. ~~Build inbound HTTP structure.~~ ✅
3. ~~Port stateless rule endpoints.~~ ✅
4. ~~Introduce request/response schemas.~~ ✅
5. ~~Extract service logic from `app.py`.~~ ✅
6. ~~Redesign inference state management.~~ ✅
7. ~~Port inference endpoints.~~ ✅
8. ~~Port file conversion endpoint.~~ ✅
9. ~~Add tests and fix test discovery.~~ ✅
10. ~~Remove duplicate legacy code and Flask dependencies.~~ ✅

## Final Repository Structure

- `src/main.py` is the FastAPI application entrypoint.
- `src/adapters/inbound/http/routes/` contains FastAPI routers (rules.py, inference.py, files.py, system.py).
- `src/adapters/outbound/persistence/` has SQLAlchemy-based repository implementation.
- `src/adapters/outbound/session/` has in-memory session store implementation.
- `src/ports/` defines abstract interfaces (SessionStorePort, RuleRepositoryPort, LLMClientPort).
- `src/schemas/` contains Pydantic request/response models.
- `src/services/` contains business logic services (RuleService, FileConversionService).
- `src/domain/inference/` contains InferenceEngine, Assessment, InferenceSession, InferenceSessionService.
- `pyproject.toml` declares FastAPI and `uvicorn` - single source of dependencies.
- Tests: 47 tests passing for services and session store.
- All legacy Flask code removed.
- Clean `src.*` import graph throughout.

---

## Current FastAPI Endpoints Summary

### Rules API (`/service/rule/...`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/service/rule/searchRuleByName` | Search rule by name |
| GET | `/service/rule/findRuleTreeDataByName` | Get rule tree data |
| GET | `/service/rule/findRuleTextByName` | Get rule text |
| GET | `/service/rule/findTheLatestRuleFileByName` | Get latest rule file |
| GET | `/service/rule/findTheLatestRuleHistoryByName` | Get latest rule history |
| GET | `/service/rule/findAllRules` | List all rules |
| POST | `/service/rule/updateRule` | Update rule |
| POST | `/service/rule/createNewRule` | Create new rule |
| POST | `/service/rule/saveConvertedRule` | Save converted rule |
| POST | `/service/rule/createFile` | Create rule file |
| GET | `/service/rule/targetNodeNameList` | Get target node names |

### Inference API (`/api/v1/inference/...`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/inference/sessions` | Create inference session |
| POST | `/api/v1/inference/sessions/ml` | Create ML-enhanced session |
| GET | `/api/v1/inference/next-question` | Get next question(s) |
| POST | `/api/v1/inference/feed-answer` | Submit answer |
| POST | `/api/v1/inference/edit-answer` | Edit previous answer |
| GET | `/api/v1/inference/summary` | Get assessment summary |
| POST | `/api/v1/inference/history` | Update rule history |

### Files API (`/api/v1/files/...`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/files/convert` | Convert document to INFERRA rules (streaming) |
| POST | `/api/v1/files/convert-to-markdown` | Convert document to markdown |

### System API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Root endpoint |
| GET | `/health` | Health check |


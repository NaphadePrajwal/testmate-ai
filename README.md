# TestMate AI

TestMate AI is an AI-driven autonomous software testing and bug analysis platform. It currently contains the Phase 0 application foundation and **Phase 1** relational backend for the core testing workflow.

## Repository layout

```text
backend/
  app/
    api/routes/       # HTTP endpoints
    core/             # settings and error handling
    db/               # SQLAlchemy engine and sessions
    models/           # persisted domain models
    schemas/          # API contracts
    services/         # domain operations
    ai/               # reserved for LangChain/LangGraph/RAG
    testing/          # reserved for Playwright/HTTPX/PyTest execution
  alembic/            # PostgreSQL migration environment and revisions
  tests/              # isolated PostgreSQL integration and API tests
frontend/
  src/
    components/       # reusable UI pieces
    hooks/            # data-loading hooks
    layouts/          # responsive dashboard frame
    pages/            # dashboard and projects views
    services/         # FastAPI client
    types/            # shared TypeScript API contracts
```

## Prerequisites

- Python 3.11 or newer (the Windows `py` launcher is supported)
- Node.js 20 or newer and npm
- PostgreSQL 15 or newer

## Backend setup

From the repository root, create and activate a virtual environment:

```powershell
py -m venv backend\.venv
.\backend\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
```

Edit `backend/.env` and set `DATABASE_URL` to your PostgreSQL database. For example:

```env
DATABASE_URL=postgresql+psycopg://testmate:testmate@localhost:5432/testmate_ai
```

Create the database once (use your PostgreSQL role as appropriate), then apply the migration:

```powershell
createdb -U postgres testmate_ai
Set-Location backend
alembic upgrade head
uvicorn app.main:app --reload
```

The API is available at `http://localhost:8000`. Its Swagger UI is at `http://localhost:8000/docs`, and its health endpoint is `http://localhost:8000/api/v1/health`.

The health endpoint always confirms whether the API process is alive; it also reports PostgreSQL as `connected` or `unavailable`, making local database setup directly verifiable.

## Frontend setup

In a second terminal from the repository root:

```powershell
Copy-Item frontend\.env.example frontend\.env
Set-Location frontend
npm install
npm run dev
```

Open the URL printed by Vite (normally `http://localhost:5173`). The top-right service indicator shows API and database connectivity. The Projects page presents loading, API-error, and empty states using the live backend API.

If the API is not running on port 8000, set `VITE_API_BASE_URL` in `frontend/.env`, for example `http://localhost:8001/api/v1`.

## Phase 2 frontend workflow

The dashboard now uses the live backend APIs for project and requirement management. Open **Projects** to create or select a project, then create, edit, view, or (when it has no dependent test cases) delete that project's requirements. The responsive mobile header includes the same Dashboard and Projects navigation as the desktop sidebar.

## Phase 3 requirement analysis

Use **Analyze** on a requirement to request an on-demand structured analysis. Results are not persisted: they represent the current stored requirement and clearly label direct source text, cautious inferences, AI suggestions, and unspecified information. Configure your preferred analysis provider (`gemini` or `openai`) in `backend/.env`:

```env
# Google Gemini API (free tier available at https://aistudio.google.com/)
AI_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash

# Alternatively, OpenAI:
# AI_PROVIDER=openai
# OPENAI_API_KEY=your_openai_key
# OPENAI_MODEL=gpt-4o-mini

ANALYSIS_TIMEOUT_SECONDS=30
```

The endpoint is `POST /api/v1/projects/{project_id}/requirements/{requirement_id}/analysis`. It returns a validated analysis plus provider/model and prompt-version metadata; it returns a safe configuration or provider error when analysis cannot run. The application does not provide generated analysis when a provider is not configured.

## Phase 4 AI test-case generation and review workflow

Use **Test Cases** on any requirement to inspect, generate, and manage test cases. The AI Test-Case Generation Agent generates positive, negative, boundary/edge cases with preconditions, ordered steps, synthetic test data, and observable expected results.

Generated test cases are persisted in PostgreSQL with `review_status = "pending"`:
- Users can review, edit, approve, or reject cases.
- Editing an unexecuted case preserves its `pending` status without auto-approving.
- Approving sets `review_status = "approved"` and `status = "approved"` (eligible for execution).
- Rejecting sets `review_status = "rejected"` and `status = "retired"`.
- Review transitions are enforced on the backend (`pending -> approved` or `pending -> rejected`).

### Phase 4 API endpoints:
- `POST /api/v1/projects/{project_id}/requirements/{requirement_id}/test-cases/generate` — Generate structured test cases using AI.
- `GET /api/v1/projects/{project_id}/requirements/{requirement_id}/test-cases` — List test cases for a requirement with optional `review_status` filter.
- `GET /api/v1/projects/{project_id}/requirements/{requirement_id}/test-cases/{test_case_id}` — Get a specific test case.
- `PATCH /api/v1/projects/{project_id}/requirements/{requirement_id}/test-cases/{test_case_id}` — Update test case specifications.
- `POST /api/v1/projects/{project_id}/requirements/{requirement_id}/test-cases/{test_case_id}/approve` — Formally approve a test case.
- `POST /api/v1/projects/{project_id}/requirements/{requirement_id}/test-cases/{test_case_id}/reject` — Reject a test case.

## Phase 5 automated test execution engine

The Test Execution Engine provides deterministic, safe, and audited test execution across three specialized adapters:

- **PlaywrightWebRunner** (`test_type="web"`): Headless Chromium browser automation with controlled locator actions (`navigate`, `click`, `fill`, `select`, `assert_text`, `assert_visible`, `assert_url`) and automatic screenshot capture on step failure or completion.
- **HttpxApiRunner** (`test_type="api"`): REST API test execution with method allowlist (`GET`, `POST`, `PUT`, `PATCH`, `DELETE`), status code assertions, response body inspection, and SSRF prevention guards blocking cloud metadata and unapproved remote hosts.
- **PytestRunner** (`test_type="manual"`): Deterministic sandboxed runner executing verified assertion templates without arbitrary script execution (`eval` or `exec`), emitting structured execution logs.

### Approval & security boundaries:
- **Approval Guard**: Test execution is strictly restricted to approved test cases (`review_status = "approved"` and `status = "approved"`). Attempting to execute pending or rejected test cases is blocked with HTTP 409 Conflict.
- **SSRF Blocklist**: Target URLs are validated against `APPROVED_API_HOSTS` and blocked from accessing cloud metadata services (`169.254.169.254`, `metadata.google.internal`).
- **Immutable Evidence**: Full execution history is persisted in `test_executions`, with binary artifacts (screenshots, logs, request/response JSON) stored on disk in `evidence_storage/` and referenced via `execution_evidence`.

### Phase 5 API endpoints:
- `POST /api/v1/projects/{project_id}/test-cases/{test_case_id}/execute` — Trigger automated test execution (optional body: `{"executor": "playwright" | "httpx" | "pytest"}`).
- `GET /api/v1/projects/{project_id}/executions` — List execution history for the project (optional query filter: `test_case_id`, `status`).
- `GET /api/v1/projects/{project_id}/executions/{execution_id}` — Get detailed execution record with step outcomes.
- `GET /api/v1/projects/{project_id}/executions/{execution_id}/evidence` — List evidence artifacts for an execution.
- `GET /api/v1/projects/{project_id}/executions/{evidence_id}/download` — Stream or download raw screenshot or log evidence.

## Phase 6 Test Results and Evidence Management

Phase 6 delivers a centralized, immutable test-results and evidence-management layer that guarantees every test run is traceable, inspectable, and safely organized for subsequent AI failure analysis.

### Core Capabilities & Architecture

1. **Execution-Time Test Case Snapshots**:
   - Every execution captures an immutable `test_case_snapshot` in PostgreSQL (`TestExecution.summary["test_case_snapshot"]`).
   - If the original test case is subsequently edited or version-bumped, past execution results remain historically accurate and reproducible.
2. **Standardized Execution Summaries & Error Categorization**:
   - Structured step counts (passed, failed, skipped, total).
   - Automated error classification via `ErrorCategory` (`assertion_failure`, `timeout`, `element_not_found`, `security_violation`, `infrastructure_error`, `unspecified`).
   - Pinpoints `failed_step_index` and preserves sanitized failure explanations.
3. **Evidence Integrity & Storage Security**:
   - Strict path containment checks (`is_relative_to(base_dir)`) prevent path traversal during file downloads.
   - Cross-project isolation: users cannot access or download evidence belonging to another project.
   - Sensitive data scrubbing: `sanitize_sensitive_data` automatically redacts credentials, passwords, tokens, API keys, and session cookies from diagnostic payloads.
   - SHA-256 checksum and byte size tracking for every stored artifact.
4. **Stable Phase 7 Data Contract**:
   - `GET /executions/{execution_id}/analysis-context` exposes `ExecutionFailureContext`, providing the AI Failure Analysis agent with structured step results, expected vs observed outputs, snapshot metadata, error category, sanitized logs, and verified evidence references without ad-hoc table joins.
5. **Interactive Frontend Results Interface**:
   - Detailed modal with chronological execution history and clear distinction between latest and historical runs.
   - Visual comparison of expected vs observed behavior for every step.
   - Screenshot preview thumbnails with fullscreen modal viewer and secure direct downloads.
   - Historical snapshot indicators displaying the executed version alongside current test case version.

### Phase 6 API Endpoints

- `GET /api/v1/projects/{project_id}/executions/{execution_id}/detail` — Retrieve full structured execution details with step results, snapshot, evidence, and defects.
- `GET /api/v1/projects/{project_id}/executions/{execution_id}/analysis-context` — Stable failure context contract for Phase 7 AI failure analysis.
- `GET /api/v1/projects/{project_id}/test-cases/{test_case_id}/history` — List chronological execution history for a specific test case with pagination.
- `GET /api/v1/projects/{project_id}/executions/{execution_id}/evidence/{evidence_id}/download` — Download authorized evidence file with path-containment validation.

## Validation commands

```powershell
# backend (from backend/ with its virtual environment activated)
# TEST_DATABASE_URL must target a dedicated database ending in _test.
$env:TEST_DATABASE_URL="postgresql+psycopg://testmate:testmate@localhost:5432/testmate_ai_test"
pytest

# frontend (from frontend/)
npm run build
npm run lint
```

## Phase 1 database architecture

PostgreSQL remains the structured system of record. The database uses this traceability chain:

```text
Project 1 ── * Requirement 1 ── * Test Case 1 ── * Test Execution
                                                       ├── * Execution Evidence
                                                       └── * Defect
```

- `requirements` are unique by project and title, and contain acceptance criteria.
- `test_cases` are unique by requirement and title, versioned on permitted updates, retain structured preconditions and steps as JSONB, and track `review_status` (`pending`, `approved`, `rejected`).
- `test_executions`, `execution_evidence`, and `defects` are append-oriented history records. Executed cases are immutable.
- UUID keys, indexed foreign keys/statuses, timezone-aware timestamps, PostgreSQL JSONB, unique constraints, and checked lifecycle values enforce durable, queryable data.
- Foreign keys use `RESTRICT`; services additionally reject deletion of a project with requirements, a requirement with cases, or a case with executions.

Apply the complete schema, including the additive migrations, with:

```powershell
Set-Location backend
alembic upgrade head
```

## API overview

All endpoints are prefixed with `/api/v1` and documented in Swagger at `/docs`.

| Resource | Endpoints |
| --- | --- |
| Projects | `GET/POST /projects`, `GET/PATCH/DELETE /projects/{project_id}` |
| Requirements | `GET/POST /projects/{project_id}/requirements`, `GET/PATCH/DELETE /projects/{project_id}/requirements/{requirement_id}` |
| Requirement Analysis | `POST /projects/{project_id}/requirements/{requirement_id}/analysis` |
| Test Case Generation & Review | `POST /projects/{project_id}/requirements/{requirement_id}/test-cases/generate`<br>`GET /projects/{project_id}/requirements/{requirement_id}/test-cases`<br>`GET/PATCH /projects/{project_id}/requirements/{requirement_id}/test-cases/{test_case_id}`<br>`POST .../{test_case_id}/approve`<br>`POST .../{test_case_id}/reject` |
| Project Test Cases (CRUD) | `GET/POST /projects/{project_id}/test-cases`, `GET/PATCH/DELETE /projects/{project_id}/test-cases/{test_case_id}` |
| Test Execution Engine | `POST /projects/{project_id}/test-cases/{test_case_id}/execute`<br>`GET /projects/{project_id}/executions`<br>`GET /projects/{project_id}/executions/{execution_id}` |
| Test Results & Failure Analysis (Phase 6) | `GET /projects/{project_id}/executions/{execution_id}/detail`<br>`GET /projects/{project_id}/executions/{execution_id}/analysis-context`<br>`GET /projects/{project_id}/test-cases/{test_case_id}/history` |
| Execution Evidence | `GET /projects/{project_id}/executions/{execution_id}/evidence`<br>`GET .../evidence/{evidence_id}`<br>`GET .../evidence/{evidence_id}/download` |
| Defects | `GET /projects/{project_id}/defects`, `GET /projects/{project_id}/defects/{defect_id}` |

Collection endpoints accept `limit` (1–100) and `offset`; lifecycle filters are available where applicable. Nested resource queries always constrain the entity to the path's project, returning `404` for cross-project access.

## Test database setup

Integration tests never use `DATABASE_URL`. Create a dedicated disposable PostgreSQL database owned by the application role, then set `TEST_DATABASE_URL` before running pytest:

```powershell
createdb -U postgres -O testmate testmate_ai_test
Set-Location backend
$env:TEST_DATABASE_URL="postgresql+psycopg://testmate:testmate@localhost:5432/testmate_ai_test"
pytest
```

The test fixture rejects names not ending in `_test`, creates only its schema there, wraps each test in a transaction, and removes the schema after the suite completes.

## Current limitations

Phase 6 implements complete test results, snapshots, evidence security/containment, and historical run management. It does not perform AI root-cause failure analysis (Phase 7), Qdrant vector retrieval/RAG (Phase 8), LangGraph multi-agent orchestration (Phase 9), intelligent test reporting (Phase 10), or self-healing test automation (Phase 12).

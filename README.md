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
- `test_cases` are unique by requirement and title, versioned on permitted updates, and retain structured preconditions and steps as JSONB.
- `test_executions`, `execution_evidence`, and `defects` are append-oriented history records. They are read-only through the Phase 1 API because execution and analysis producers are later-phase work.
- UUID keys, indexed foreign keys/statuses, timezone-aware timestamps, PostgreSQL JSONB, unique constraints, and checked lifecycle values enforce durable, queryable data.
- Foreign keys use `RESTRICT`; services additionally reject deletion of a project with requirements, a requirement with cases, or a case with executions. Executed cases are immutable.

Apply the complete schema, including the additive Phase 1 migration, with:

```powershell
Set-Location backend
alembic upgrade head
```

The migration is additive to the Phase 0 `projects` table and does not rewrite or delete its data.

## API overview

All endpoints are prefixed with `/api/v1` and documented in Swagger at `/docs`.

| Resource | Endpoints |
| --- | --- |
| Projects | `GET/POST /projects`, `GET/PATCH/DELETE /projects/{project_id}` |
| Requirements | `GET/POST /projects/{project_id}/requirements`, `GET/PATCH/DELETE /projects/{project_id}/requirements/{requirement_id}` |
| Test cases | `GET/POST /projects/{project_id}/test-cases`, `GET/PATCH/DELETE /projects/{project_id}/test-cases/{test_case_id}` |
| Execution history | `GET /projects/{project_id}/executions`, `GET /projects/{project_id}/executions/{execution_id}` |
| Execution evidence | `GET /projects/{project_id}/executions/{execution_id}/evidence` and `/{evidence_id}` |
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

This phase does not generate test cases, run browser/API tests, use multi-step agent frameworks, use RAG/vector storage, or perform execution failure analysis. It intentionally does not expose write endpoints for execution, evidence, or defect records; their controlled producers will be introduced in later phases. PostgreSQL must be running with configured credentials for data APIs and migrations to work.

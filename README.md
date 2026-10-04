# TestMate AI

TestMate AI is an AI-driven autonomous software testing and bug analysis platform. This repository currently contains **Phase 0**, a production-minded foundation for its FastAPI backend, PostgreSQL persistence, React dashboard, and backend/frontend integration.

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
  tests/              # backend foundation tests
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

## Validation commands

```powershell
# backend (from backend/ with its virtual environment activated)
pytest

# frontend (from frontend/)
npm run build
npm run lint
```

## Database scope

The only Phase 0 table is `projects`, because it backs the actual project-listing API and dashboard state. The architecture intentionally reserves separate modules for future users, requirements, test cases, executions, results, bug reports, historical knowledge, RAG, agents, and reporting instead of creating unused schema or mock functionality.

## Current limitations

Phase 0 does not generate tests, run browsers/APIs, call LLMs, or create artificial results. PostgreSQL must be running with the configured credentials for project listing and migrations to work.

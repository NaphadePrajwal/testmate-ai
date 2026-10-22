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

## Phase 8 Historical Bug Intelligence (Qdrant & SentenceTransformers)

TestMate AI integrates vector retrieval for historical failure intelligence, resolved bugs, and regression test cases:

- **Vector Database (Qdrant):** Managed via `QdrantService` (`backend/app/services/qdrant_service.py`), supporting `server` (standalone Qdrant on port 6333), `local` (embedded disk directory storage in `qdrant_storage`), and `memory` (transient in-memory storage for testing).
- **Embedding Service (SentenceTransformers):** Managed via `EmbeddingService` (`backend/app/services/embedding_service.py`) using `sentence-transformers/all-MiniLM-L6-v2`:
  - **Vector Dimensions:** Exactly 384 dimensions, normalized with Cosine similarity for direct Qdrant index compatibility.
  - **Model Lifecycle & Caching:** In-memory thread-safe model caching reuses loaded weights across requests without reloading.
  - **CPU-Friendly Execution:** Configured for `cpu` device by default with configurable batch sizes (`EMBEDDING_BATCH_SIZE=32`), requiring no GPU hardware.
  - **Model Download Behavior:** Weights are loaded lazily on the first live embedding call; unit tests use deterministic mock doubles without requiring internet access or model downloads.

### Usage Example:
```python
from app.services.embedding_service import EmbeddingService

embedding_service = EmbeddingService()

# Single-text embedding
vector = embedding_service.embed_text("AssertionError: Expected 200 OK, got 500 Internal Server Error")
assert len(vector) == 384

# Batch embedding
vectors = embedding_service.embed_batch([
    "AssertionError: Expected 200 OK, got 500",
    "TimeoutError: Page element not found within 15000ms",
])
```

### Running Vector & Embedding Tests:
```powershell
Set-Location backend
$env:TEST_DATABASE_URL="postgresql+psycopg://testmate:testmate@localhost:5432/testmate_ai_test"
pytest tests/test_qdrant_service.py tests/test_embedding_service.py tests/test_knowledge_document_service.py -v
```

### Historical Knowledge Preparation (Phase 8.4):
- **Document Model (`PreparedKnowledgeDocument`):** Standardizes historical entities across 3 distinct knowledge record types:
  1. `defect`: Captures defect title, description, severity, status, and associated failure traces. Explicitly marks resolution status without fabricating unverified root-cause documentation.
  2. `failure_analysis`: Prepares AI diagnostic summaries, observed errors, and suggested debugging steps while strictly demarcating them as diagnostic hypotheses rather than confirmed resolutions.
  3. `test_case`: Formats test descriptions, preconditions, structured step traces, and expected outcomes into clean searchable text.
- **Tenant Isolation:** Enforces authoritative `project_id` on all prepared documents to guarantee cross-tenant isolation in subsequent vector indexing and semantic retrieval.
- **Separation of Concerns:** Pure transformation layer (`KnowledgeDocumentService`) separating dense searchable text for embeddings from filterable metadata for Qdrant payload filters.

### Knowledge Base Indexing Pipeline (Phase 8.5):
- **Indexing Service (`KnowledgeBaseService`):** Orchestrates the end-to-end indexing pipeline connecting `KnowledgeDocumentService`, `EmbeddingService`, and `QdrantService` (`backend/app/services/knowledge_base_service.py`).
- **Deterministic Point Identifiers:**
  - Uses UUIDv5 derived from `uuid.uuid5(TESTMATE_KNOWLEDGE_NAMESPACE, f"{record_type}:{source_id}")`.
  - Guarantees idempotent upserts: re-indexing an existing record updates the existing vector and metadata in place without creating duplicate points.
  - Eliminates cross-type collisions by including the record type prefix.
- **Payload & Metadata Serialization:**
  - Preserves core filterable fields: `record_type`, `source_id`, `project_id`, `title`, `search_text`, `is_verified_resolution`, and `created_at`.
  - Flattens bounded metadata (`severity`, `status`, `test_type`, `fingerprint`, etc.) into JSON-clean primitives compatible with Qdrant index filtering.
  - Keeps PostgreSQL as the authoritative source of truth.
- **Batch Processing & Error Resilience:**
  - Configurable batch processing (`batch_size=32`) to optimize vector throughput while bounding memory usage.
  - Granular error capture (`IndexingErrorItem`): embedding timeouts or Qdrant transport errors report partial failure diagnostics without halting the entire pipeline or claiming false successes.
- **Project-Scoped Tenant Isolation:**
  - Queries strictly filter on `project_id` to prevent cross-tenant record leakage.
  - Exposes `POST /api/v1/projects/{project_id}/knowledge/index` allowing on-demand indexing with optional `record_types` filtering.
- **Single-Entity Helpers:**
  - Provides targeted methods (`index_single_defect`, `index_single_failure_analysis`, `index_single_test_case`, `delete_point`) for incremental sync as entities are created, updated, or removed.

### Running Historical Knowledge Tests:
```powershell
Set-Location backend
$env:TEST_DATABASE_URL="postgresql+psycopg://testmate:testmate@localhost:5432/testmate_ai_test"
pytest tests/test_qdrant_service.py tests/test_embedding_service.py tests/test_knowledge_document_service.py tests/test_knowledge_base_service.py tests/test_knowledge_retrieval_service.py -v
```

### Semantic Retrieval Services (Phase 8.6):
- **Retrieval Service (`KnowledgeRetrievalService`):** Orchestrates semantic vector search across historical QA records in Qdrant (`backend/app/services/knowledge_retrieval_service.py`).
- **Query Embedding Generation:** Converts search queries (failure descriptions, stack traces, questions) into normalized 384-d vectors using `EmbeddingService.embed_text`.
- **Mandatory Tenant Isolation:** Strict Qdrant payload filtering (`models.Filter` with `FieldCondition(key="project_id", match=MatchValue(value=project_id))`) enforced at query time. Never allows cross-tenant vector leakage.
- **Record-Type Filtering:** Supports targeting specific knowledge types (`defect`, `failure_analysis`, `test_case`) via `MatchAny` filtering.
- **Similarity Thresholding & Ranking:**
  - Configurable minimum cosine similarity threshold (`min_score`, default `0.4`, bound between `0.0` and `1.0`) applied directly via Qdrant's `score_threshold`.
  - Configurable candidate limit (`limit`, default `5`, bound between `1` and `50`), returning results in descending score order.
  - Automatic deduplication of source records (`record_type`, `source_id`).
- **REST API Endpoint:**
  - `POST /api/v1/projects/{project_id}/knowledge/search` — Accepts `query`, `record_types`, `limit`, and `min_score`. Returns structured `KnowledgeSearchResponse` with candidate metadata and similarity scores.
- **Interpretability & Grounding:**
  - Similarity scores quantify contextual and semantic text closeness, not diagnostic certainty that two failures share an identical root cause.

### Bug Analysis Agent RAG Integration (Phase 8.7):
- **Retrieval-Augmented Diagnosis (`FailureAnalysisService`):**
  - Seamlessly integrates `KnowledgeRetrievalService` into the failure analysis pipeline (`backend/app/services/failure_analysis_service.py`).
  - Automatically extracts a bounded search query from execution error reasons, failed step actions, and test metadata (`extract_failure_search_query`).
  - Scopes retrieval strictly to the execution's authoritative `project_id`.
  - Attaches relevant historical candidates directly to `ExecutionFailureContext.historical_candidates`.
- **Prompt-Injection Hardening & Delimiter Boundaries:**
  - Retrieved historical records are encapsulated in a strictly demarcated `<untrusted_historical_knowledge>` block.
  - Prompt instructions explicitly command LLMs (OpenAI and Gemini) to treat historical data as passive evidence, never as executable instructions.
  - Neutralizes nested XML tags (`</untrusted_historical_knowledge>`, `<historical_candidate>`, etc.) inside retrieved text to prevent prompt breakout attacks.
- **Epistemic Distinctions (Verified vs. Hypothesized):**
  - Defect tracker resolution status is explicitly labeled as tracker resolution without fabricating unverified technical post-mortems.
  - Past AI diagnostic records are explicitly labeled as `PRIOR AI-GENERATED DIAGNOSTIC HYPOTHESIS` (non-verified).
  - High cosine similarity scores are presented as contextual relevance signals, instructing the LLM never to claim shared root cause without corroborating failure traces.
- **Resilient Fallback Behavior:**
  - If Qdrant is offline, vector queries time out, or zero candidates match, the system logs diagnostic telemetry and falls back gracefully to standard Phase 7 failure diagnosis.
  - Cached analyses bypass vector queries to avoid redundant retrieval overhead.
- **Multi-Provider Support:**
  - Both `OpenAIFailureAnalysisProvider` and `GeminiFailureAnalysisProvider` consume the same shared prompt builder (`build_failure_analysis_prompt`), ensuring identical RAG context and injection protections across models.

### Automatic Knowledge Indexing & Resolution Lifecycle (Phase 8.8):
- **Durable Outbox Indexing Queue (`knowledge_indexing_jobs`):**
  - PostgreSQL-backed transactional outbox queue decoupling application database transactions from external vector database operations.
  - Asynchronous / non-blocking dispatch: Qdrant downtime never blocks primary business workflows (defect creation, test case edits, failure analysis).
  - Configurable exponential retry policy (`max_retries = 3`) with persistent error audit logs and safe state tracking (`pending`, `processing`, `completed`, `failed`).
- **Defect Resolution & Verification Lifecycle:**
  - Enforces strict epistemic distinction between unresolved defects, resolved-but-unverified defects, verified technical fixes, and AI-generated hypotheses.
  - Transitioning a defect to `VERIFIED` requires documented `resolution_notes` and verification metadata (`verification_method`, `verification_evidence`).
  - Merely marking a defect `RESOLVED` or `CLOSED` explicitly retains `is_verified_resolution = False` in vector embeddings and search payloads.
  - Revoking verification (`REVOKED` or unverified status) automatically synchronizes to Qdrant, purging stale verified-resolution claims.
- **Automatic Indexing Triggers:**
  - **Failure Analyses:** Enqueued upon successful completion/persistence of new or re-analyzed execution failures; skips on cached retrieval hits.
  - **Defects:** Automatically enqueued on creation (e.g. from execution failure) or update (`PATCH /api/v1/projects/{project_id}/defects/{defect_id}`).
  - **Test Cases:** Enqueued upon creation, update, approval, or deletion (triggers vector deletion).
- **Reconciliation & Batch Job Processing:**
  - `PATCH /api/v1/projects/{project_id}/defects/{defect_id}` — Update defect status, resolution notes, and technical verification metadata.
  - `GET /api/v1/projects/{project_id}/knowledge/jobs` — Inspect queue state and diagnose indexing issues.
  - `POST /api/v1/projects/{project_id}/knowledge/jobs/process` — Manually trigger batch reconciliation/retry of pending or failed indexing operations.
  - `POST /api/v1/projects/{project_id}/knowledge/index` — Full-project reindexing automatically resolves pending/failed queue jobs upon completion.

### Running Historical Knowledge & RAG Tests:
```powershell
Set-Location backend
$env:TEST_DATABASE_URL="postgresql+psycopg://testmate:testmate@localhost:5432/testmate_ai_test"
pytest tests/test_qdrant_service.py tests/test_embedding_service.py tests/test_knowledge_document_service.py tests/test_knowledge_base_service.py tests/test_knowledge_retrieval_service.py tests/test_failure_analysis_rag.py tests/test_knowledge_indexing_e2e.py -v
```

## Phase 9 — Multi-Agent Workflow Using LangGraph

Phase 9 connects TestMate AI's autonomous capabilities into a genuine, stateful, multi-agent workflow orchestrated via **LangGraph**.

### Workflow Architecture & State Machine

```text
[START]
   │
   ▼
1. Validate Context Node (Validate project & requirement association)
   │
   ▼
2. Requirement Analysis Agent Node (Invoke AI requirement analysis service)
   │
   ▼
3. Test Case Generation Agent Node (Synthesize structured test cases from validated analysis)
   │
   ▼
4. Human Approval Checkpoint (Interrupt execution & persist state via PostgresSaver)
   │
   ├── REJECT ──────────────► Record Rejection ──► [END] (Zero executions)
   │
   ├── REQUEST REVISION ────► Apply Revision Feedback ──► (Loop back to Test Case Generation)
   │
   └── APPROVE ─────────────► Validate Approval
                                   │
                                   ▼
                              5. Test Execution Node (Run approved cases via Execution Service)
                                   │
                                   ▼
                             [Evaluate Execution Outcomes]
                                   │
                    ┌──────────────┴──────────────┐
                    ▼                             ▼
             [All Passed]                 [Failures Found]
                    │                             │
                    ▼                             ▼
           Record Success Node         6. Historical RAG Node (Query project-scoped Qdrant knowledge)
                    │                             │
                    ▼                             ▼
                  [END]                7. Failure Analysis Agent Node (AI root cause diagnosis)
                                                  │
                                                  ▼
                                                [END]
```

### Key Capabilities

1. **Stateful Graph Orchestration (`app.orchestration.graph`):**
   - Built and compiled using `langgraph.graph.StateGraph` with typed shared state (`WorkflowGraphState`).
   - Every major lifecycle phase is a first-class graph node communicating purely through validated state.
   - Nodes only update their owned keys; invalid state transitions are bounded and rejected.

2. **Human Approval Checkpoint Interruption:**
   - Implemented using LangGraph's native `interrupt(...)` mechanism.
   - When test cases are synthesized, execution suspends deterministically and returns `paused_for_approval` status.
   - Execution strictly **cannot** proceed to test execution without human review.
   - Reviewers can:
     - **Approve:** Resumes execution via `Command(resume=...)`, executing test cases.
     - **Reject:** Cleanly terminates the workflow with zero executions and marks status `rejected`.
     - **Request Revision:** Captures reviewer feedback instructions, routes back to generation, and pauses for review again.

3. **Conditional Routing Based on Real Execution Results:**
   - Evaluates real test execution results (`passed_count`, `failed_count`, `error_count`).
   - **All Passed:** Routes to `record_success`, completely bypassing RAG and failure analysis.
   - **Failures Found:** Routes to `historical_rag` to retrieve matching defect/failure precedents from Qdrant, passing retrieved context into `failure_analysis`.

4. **Persistent PostgreSQL Checkpointing (`PostgresSaver`):**
   - Backed by PostgreSQL (`langgraph-checkpoint-postgres`), ensuring workflow state and checkpoints survive process restarts.
   - Domain workflow metadata (`WorkflowExecution`) and chronological stage events (`WorkflowEvent`) are persisted in PostgreSQL.
   - Internal checkpoint tables (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations`) are safely isolated and excluded from Alembic schema drift tracking.

5. **FastAPI Endpoints:**
   - `POST /api/v1/projects/{project_id}/workflows` — Initialize and start workflow for a requirement (pauses at approval checkpoint).
   - `GET /api/v1/projects/{project_id}/workflows` — List workflows for a project or requirement.
   - `GET /api/v1/projects/{project_id}/workflows/{workflow_id}` — Retrieve workflow state, current stage, generated cases, and executions.
   - `GET /api/v1/projects/{project_id}/workflows/{workflow_id}/history` — Retrieve chronological audit log of stage transitions.
   - `POST /api/v1/projects/{project_id}/workflows/{workflow_id}/approval` — Submit human approval decision (`approve`, `reject`, `request_revision`).

6. **Frontend Integration:**
   - Responsive `MultiAgentWorkflowPanel` embedded directly into requirement cards on the Project details page.
   - Displays live 5-stage stepper visualization with real-time status badges.
   - Interactive Human Approval Checkpoint allowing one-click approval, revision requests, or rejections.
   - Expandable stage transition audit log.

### Running Phase 9 Tests:

```powershell
Set-Location backend
$env:TEST_DATABASE_URL="postgresql+psycopg://testmate:testmate@localhost:5432/testmate_ai_test"
pytest tests/test_multi_agent_workflow.py -v
```

### Running All Regression Tests:

```powershell
Set-Location backend
$env:TEST_DATABASE_URL="postgresql+psycopg://testmate:testmate@localhost:5432/testmate_ai_test"
pytest -q
```

## Phase 10 — Autonomous Browser Testing & Intelligent Test Orchestration

Phase 10 enables TestMate AI to execute approved test cases against real web applications, capture structured execution evidence (screenshots, console logs, network errors), and integrate execution results with the LangGraph workflow and AI failure analysis.

### Architecture & Capabilities

1. **Playwright Browser Runner (`app.testing.playwright_runner`):**
   - Headless Chromium browser automation via the official `playwright` Python package.
   - Dynamic locator resolution with accessibility-first priority:
     - `role` & `name` (`page.get_by_role(role, name=name)`)
     - `label` (`page.get_by_label(...)`)
     - `placeholder` (`page.get_by_placeholder(...)`)
     - `test_id` (`page.get_by_test_id(...)`)
     - `text` (`page.get_by_text(...)`)
     - Standard CSS/XPath selector fallback
   - Supported structured actions:
     - `navigate`: Navigate to target URL with pre-navigation and redirect validation.
     - `click`: Click accessible buttons, links, or inputs.
     - `fill`: Populate form fields and inputs.
     - `select`: Choose option by value or label in `<select>` elements.
     - `check` / `uncheck`: Toggle accessible checkboxes and radios.
     - `assert_visible`: Verify visible presence of an element on screen.
     - `assert_text`: Verify exact or substring text visible on screen.
     - `assert_title`: Assert browser tab title.
     - `assert_url`: Assert current URL or path.
     - `wait_for`: Bounded wait for element or timeout.

2. **Target Application Safety & SSRF Protection (`app.core.url_utils`):**
   - Strict scheme enforcement (permitting only `http` and `https`).
   - Embedded credentials rejection (`user:pass@host` immediately rejected).
   - Loopback and local testing safety: allowed on designated localhost/127.0.0.1 ports for test fixtures.
   - Cloud metadata blocking: `169.254.169.254` and link-local ranges explicitly rejected.
   - Pre-navigation destination revalidation and redirect inspection.

3. **Structured Evidence & Defect Auto-Creation (`ExecutionEvidence`):**
   - High-resolution viewport screenshot capture on test failure and on completion.
   - Browser console logs, unhandled page errors, and failed network requests captured into `ExecutionEvidence`.
   - Distinguishes test assertion failures (`ExecutionStatus.FAILED`, `ErrorCategory.ASSERTION_FAILURE`) from infrastructure errors (`ExecutionStatus.ERROR`, `ErrorCategory.INFRASTRUCTURE_ERROR`).
   - Generates and links a PostgreSQL `Defect` on assertion failure.

4. **Safe Local Demonstration Storefront (`/api/v1/demo/storefront`):**
   - Self-contained, isolated e-commerce demo application served directly by FastAPI.
   - Features product browsing, cart addition, live cart badge count, and checkout payment form.
   - Supports deliberate failure testing: entering card number `0000` or `fail` triggers simulated payment decline.

5. **Frontend Results & Evidence Inspector:**
   - Expandable execution cards inside `MultiAgentWorkflowPanel.tsx`.
   - Chronological step-by-step breakdown with action badges, status badges, expected vs. actual outcomes, and step duration in ms.
   - Screenshot gallery with click-to-zoom modal for detailed visual inspection.
   - Download links for captured diagnostic logs and screenshots.
   - Direct links to auto-created defects.

### Isolated PostgreSQL Integration Test Infrastructure

To ensure zero risk to development and production databases:
- The integration test harness (`backend/tests/conftest.py`) requires an isolated test database configured via `TEST_DATABASE_URL` (e.g. `testmate_test`).
- Rejects any target database named `testmate_ai`, `postgres`, `production`, or pointing to non-loopback hosts.
- Automatically loads `backend/.env.test` (ignored by Git).
- Creates schema fixtures, executes tests within isolated transactions, and cleans up safely without leaving residue.

### Running Phase 10 Tests

```powershell
# 1. Ensure Playwright browser binaries are installed
playwright install chromium

# 2. Run Autonomous Browser Testing test suite
Set-Location backend
$env:TEST_DATABASE_URL="postgresql+psycopg://testmate:testmate@localhost:5432/testmate_test"
pytest tests/test_autonomous_browser_testing.py -v

# 3. Run full backend suite (167 tests)
pytest -q

# 4. Check Alembic schema drift
alembic check

# 5. Frontend lint and production build
Set-Location ../frontend
npm run lint
npm run build
```

## Current limitations

Phases 1–10 are fully implemented and verified across the backend automated test suite (167 passed tests), live Playwright browser runs, Alembic migrations, and the React frontend dashboard. External third-party websites outside approved domains are blocked by default for safety. Production deployments should run Playwright inside isolated containers or sandboxes.


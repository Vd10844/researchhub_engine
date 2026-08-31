# mapperty-reference (QuickPlot API) — Technical Map for Integration

The parent product the QuickPlot / researchhub-engine is being merged into. This map is organized to the 11 questions asked, with file paths and line references. Read-only — nothing was modified.

> **Headline finding:** the parent is a mature multi-tenant FastAPI monolith (Cognito auth, billing/credits, identity, evidence/S3), but the **`research` module is a completely empty slot** and **nothing in the parent references the engine yet**. Also, there is **no real `orders` table and no `order_files` table** — the two tables the engine's migration `0001` FKs into don't exist here. Those are the real integration gaps.

---

## 1. Top-level structure

- **App type:** FastAPI monolith. Title "QuickPlot API" (`app/main.py:95`). Root `/` returns `{"message":"Quickplot API is running"}`; `/health` returns status. SQLAdmin UI mounted at `/admin`.
- **Python / deps:** `pyproject.toml` (2.8KB) + `poetry.lock` (426KB) — **Poetry**, not requirements.txt. (The engine's requirements.txt says it is pinned to match this pyproject.) `pytest.ini` present.
- **Run:** `start-api.bat` (local), `Dockerfile` (778B) + `docker-compose.yml` (2.2KB), `nginx/` + `infrastructure/` dirs, GitHub Actions in `.github/` (the `deploy-dev.yml` the engine docs cite). Celery worker via `app/workers/celery_app.py`.
- **Config:** `app/core/config.py` — pydantic-settings; secrets injected by **ECS from AWS Secrets Manager** at runtime (DATABASE_URL, Cognito, Stripe). Postgres `postgresql+psycopg2://…:5432/…` (`config.py:50-53`). `RUN_ENV` gates local vs prod.
- **Root docs:** `README.md` (17 bytes — empty), plus `AGENTS.md`, `CLAUDE.md`, `COGNITO_INTEGRATION.md` (15KB), `ENV_SETUP.md`, `IMPLEMENTATION_SUMMARY.md` (14KB).

---

## 2. `app/modules/` — all modules

| Module | State | Contents / purpose |
|---|---|---|
| **identity** | **Full, large** | Cognito auth, users, tenants, roles, permissions, sessions, notifications. `service.py` 229KB, `models.py` 65KB, `dependencies.py` 29KB, `routers/` (auth 56KB, organization 41KB, roles, users, notifications, websockets). The core of the app. |
| **billing** | **Full, largest** | Subscriptions, plans, credits, Stripe. `service.py` 356KB, `models.py` 96KB, `routers/` (checkout 52KB, webhook 79KB, credits, downgrade, enterprise, seats, plans, admin). |
| **evidence** | **Full** | File storage over S3. `models.py` (File), `repository.py`, `service.py` (S3Service), `routers/file_handler.py`, `utils.py`. See Q5. |
| **legal_documents** | **Full** | Policy documents + user guides, versioned. router/service/models present. |
| **orders** | **Stub (misleading name)** | NOT order management. `models.py` = abstract stub only (Q3). Real code = `services/property_deed_workorder.py` (18KB) + `router.py` → an **LLM document-extraction** endpoint `POST /v1/extraction/property-deed` (parses deed/workorder files into structured `PropertyDeedData`). No Order entity. |
| **research** | **EMPTY slot** | `models.py` 0B, `router.py` 0B, `tasks.py` 0B, `schemas/v1/research.py` 0B; `state_machine.py` = `class StateMachine: pass`; `__init__.py` has a stray docstring copied from "Policy Documents". Not mounted in `main.py`. **This is where the engine lands.** |
| **cad, exports, field, jobs, qc, quotes** | **Empty stubs** | Each is `models.py`/`service.py`/`repository.py` 0-78 bytes, `router.py` a bare `APIRouter`, `state_machine.py`=`pass`. Placeholders for future modules. |

Also: `app/admin/` (SQLAdmin views), `app/core/` (auth/config/middleware/exceptions/…), `app/db/`, `app/integrations/` (arcgis/aws/mapbox/oda/openai — each just `__init__`+ a 28-byte `client.py` stub), `app/scheduled_jobs/`, `app/schemas/v1/`, `app/workers/`.

Router wiring (`main.py:150-165`): `/v1` mounts identity, legal_documents, evidence, orders extraction, and all billing routers. **research is NOT included.**

---

## 3. `app/modules/orders/models.py` — EXACT content

Confirmed — it is a 3-line abstract base, not an order model (78 bytes, leading BOM):

```python
from app.db.base import Base
class Model(Base):
    __abstract__ = True
```

`orders/service.py` is likewise `class Service: pass`. There is **no `Order` table** anywhere in the parent.

---

## 4. References to the engine / its tables

Grep across everything staged (`app/**`) for `researchhub`, `research_api`, `research_jobs`, `research_documents`, `order_files`, `OrderFile`, `/api/v1/research` → **zero matches.** The parent has no awareness of the engine yet; `db/models.py:` imports `app.modules.research.models` but that file is empty. Integration is greenfield inside the `research` module.

*(Caveat: `nginx/`, `infrastructure/`, `.github/`, and the root `*.md` docs were not fully read; the engine's own docs quote the parent's `deploy-dev.yml`, so CI references likely live there — worth a direct grep of those dirs.)*

---

## 5. Evidence module — File model & storage

`modules/evidence/models.py` — one model, `File` (table `files`), mixins `Audit + Timestamp + Tenant + SoftDelete`:

| Column | Type |
|---|---|
| filename | String(512) |
| file_path | String(2048), indexed — the S3 key |
| file_size | BIGINT nullable |
| status | enum `file_status_enum` (`uploading`/`uploaded`) |
| + id (UUID), tenant_id, created/updated_by, timestamps, deleted_at |

- **Tenant scoping:** yes, via `TenantMixin`; all repo queries filter `tenant_id` (`repository.py`).
- **Blob storage:** `service.py:S3Service` — boto3, single bucket `settings.S3_ARTIFACTS_BUCKET` (`quickplot-dev-artifacts`), presigned GET/PUT/DELETE, multipart upload. Key scheme `tenants/{tenant_id}/orders/{order_id}/client_file/...` (`utils.py:24,61`).
- **Order link:** `repository.count_files_for_order` and `utils.py` use an **`order_id`** on/around File and parse it from the S3 key — but the staged `models.py` does **not declare an `order_id` column** (verify against the live file). There is **no `OrderFile` join table** in the parent.

**Mismatch vs engine's evidence stand-in:** engine expects `files(content_key, size, sha256, mime_type)` + a separate `order_files` join; parent has `files(file_path, file_size, status)` keyed by S3 path, no `sha256`/`content_key`, no `order_files`. The engine's `adapters._create_evidence_rows` / `evidence_source.create_evidence` will need rewriting to the parent's `File` shape (and the `research_documents.order_file_id` FK dropped or repointed).

---

## 6. Auth / identity

- **Cognito JWT.** `core/auth_middleware.py:AuthMiddleware` extracts the `Authorization: Bearer` token, validates via `core/cognito_jwt.py:CognitoJWTValidator` (JWKS cached 1h, signature/issuer/audience/expiry), and stashes `request.state.token_payload` + `request.state.user_sub`. It does **not** require auth globally (has a large `EXEMPT_PATHS` set); endpoints enforce via dependencies. Web uses a cookie token, iOS/mobile uses the Bearer header.
- **Actor derivation:** `identity/dependencies.py:get_current_user` resolves the `User` from the token (cookie or bearer), validates an active `UserSession`, and calls `set_current_user_id` for history stamping.
- **Tenant derivation:** header-based — `get_current_tenant_id(x_tenant_id: UUID = Header(..., alias="X-Tenant-ID"))` (`dependencies.py:409`), validated against the user's memberships/session (`validate_tenant_context`, `:350`). Postgres **RLS**: `get_db` issues `SET LOCAL app.current_tenant = :tenant_id` (`core/dependencies.py`).
- **Maps cleanly to the engine:** engine's placeholder `X-Actor-Id`/`X-Tenant-Id` deps become `get_current_user` + `get_current_tenant_id`. Config already carries the Cognito fields (`config.py:92-113`). `COGNITO_INTEGRATION.md` (root, 15KB) documents the scheme.

---

## 7. Database

- **Alembic:** root `alembic.ini` + `app/db/migrations/` (`env.py`, `versions/`). **31 revisions**; initial `65f9f7124cfd_initial_migration.py` (28KB); two merge revisions (`6be425ab7079`, `c424fd2909f7`) → single head. sqlalchemy-history versioning tables (`4a706c6e6dbe`, 52KB). Chains cover identity/tenants/users/roles/permissions/sessions, billing/credits/subscriptions, legal_documents, scheduled_jobs.
- **Engine/session:** `db/base.py` — sync `SessionLocal` + engine, optional `AsyncSessionLocal`; `db/versioning.py` (sqlalchemy-history), `db/mixins.py` (Audit/Timestamp/Tenant/SoftDelete — same conventions the engine copied), `db/models.py` imports all ORM models (incl. empty `research.models`).
- **Postgres**, port 5432, `postgresql+psycopg2`; URL from Secrets Manager (`config.py:50-53`).
- **For the engine merge:** the engine's `0001` must be re-parented onto this chain's head (dropping engine `0002`), and its FKs to `orders`/`order_files` resolved — neither table exists here yet.

---

## 8. Deployment

- **AWS `us-east-1` ECS** (from engine docs quoting the parent `deploy-dev.yml`): ECR `quickplot-api` → cluster `quickplot-dev` with `quickplot-dev-api` + `quickplot-dev-worker`; **Cognito** pool `us-east-1_EHikamkop`; secrets (`APP_SECRET_KEY`, `COGNITO_CLIENT_SECRET`, `STRIPE_SECRET_KEY`) in Secrets Manager; `alembic upgrade head` as a one-off ECS task in-VPC.
- **In-repo:** `Dockerfile`, `docker-compose.yml`, `nginx/` (reverse proxy — not read), `infrastructure/` (IaC — not read), `.dockerignore`.
- **Nginx / ALB:** TLS terminates at the ALB, ALB→ECS is plain HTTP; `SchemeFromForwardedProtoMiddleware` + hand-rolled X-Forwarded-For parsing (takes the LAST entry) handle the proxy hop (`main.py:150+`, `auth_middleware.py:dispatch`).
- **US egress:** native — a US-region host satisfies FEMA/county geo-blocks with no VPN (the engine's whole egress problem is solved by deploying inside the parent). AWS region locked to `us-east-1` throughout config.

---

## 9. Frontend

The parent **serves no UI**: `main.py` has no `StaticFiles` mount and no HTML routes — `/` returns JSON, the only mounted app is SQLAdmin at `/admin`. **QuickPlot's `quickplot.html` is NOT present here** and is not served by this API; it must be copied in / hosted separately (or served by nginx) as part of integration. (The engine's `docs/technical-briefing/03-frontend-deep-dive.md` describes the QuickPlot UI as a separate concern.)

---

## 10. Integration notes in docs / comments

Not fully read, but present at root and worth reading directly: `IMPLEMENTATION_SUMMARY.md` (14KB), `COGNITO_INTEGRATION.md` (15KB), `AGENTS.md`, `CLAUDE.md`, `ENV_SETUP.md`. No survey/research-specific integration note was found in the staged `app/**` code. The authoritative integration plan lives on the engine side (`researchhub-engine/docs/technical-briefing/*` + `api-contract-freeze.md`), which explicitly describes dropping into `app/modules/research/`.

---

## 11. TODO / FIXME / stub markers = intended integration points

- **`app/modules/research/`** — the entire module is empty files: `models.py`, `router.py`, `tasks.py`, `schemas/v1/research.py` all 0 bytes; `state_machine.py`=`pass`; `routers/__init__.py` bare. This is the designated destination for the engine (models → here, router → mounted in `main.py`'s `v1_router`, tasks → Celery).
- **`db/models.py`** already imports `app.modules.research.models` — the loader hook is pre-wired for the engine's models.
- **`schemas/v1/research.py`** (empty) — the slot for the engine's API schemas.
- **`workers/tasks/research_tasks.py`** (empty) + `workers/celery_app.py` — the slot for the research Celery task/queue.
- **`orders` module** is a naming collision to resolve: it currently holds only LLM extraction; the engine assumes a real `orders` table. Decide whether to build the Order entity here or adapt the engine's `order_provider` to whatever represents an order in the parent.
- Empty `integrations/*/client.py` stubs (arcgis/aws/mapbox/oda/openai) suggest intended homes for external clients the engine's `services/` already implement.

---

### Net for developers
Wiring the engine in means: (1) move `engine/` models/schemas/router/worker into `modules/research` + `schemas/v1/research.py` + `workers/tasks/research_tasks.py`; (2) mount the research router in `main.py`'s `v1_router`; (3) replace the engine's placeholder auth deps with `identity.get_current_user` / `get_current_tenant_id`; (4) re-parent the alembic `0001` migration onto this chain's head and drop engine `0002`; (5) **build/define the `orders` entity** the engine depends on; (6) reconcile the engine's evidence writes (`content_key/size/sha256` + `order_files`) with the parent's `evidence.File` (`file_path/file_size/status`, no join table); (7) copy in / host the QuickPlot frontend separately.

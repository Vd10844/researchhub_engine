# Version Parity Plan — Engine vs Mapperty Parent

**Reference repo:** `../mapperty-reference` (mapperty/quickplot-api, cloned 2026-08-25)
**Our repo:** `./` (researchhub-engine)

---

## Library alignment: what we have vs what they pin

| Category | Mapperty pins (pyproject.toml) | Our current (requirements.txt) | Gap? | Action |
|----------|-------------------------------|--------------------------------|------|--------|
| **Core** | | | | |
| fastapi | 0.111.0 | >=0.115 | **YES** — we're NEWER | Pin to 0.111.0 (or 0.115+ if they're about to upgrade; confirm with them) |
| uvicorn[standard] | 0.30.0 | >=0.30 | Compatible | Match to 0.30.0 |
| pydantic | 2.10.0 | >=2.9 | **YES** — we're older | Bump to 2.10.0 |
| pydantic-settings | 2.3.4 | (missing) | **YES** | Add pydantic-settings==2.3.4 |
| **Database** | | | | |
| sqlalchemy | 2.0.46 | >=2.0 | Compatible | Match to 2.0.46 |
| alembic | 1.13.2 | (missing) | **YES** | Add alembic==1.13.2 |
| psycopg2-binary | 2.9.10 | >=2.9 | Compatible | Match to 2.9.10 |
| psycopg[binary] | ^3.2.0 | (missing) | **YES** | Add psycopg[binary]>=3.2.0 |
| **Auth (future)** | | | | |
| python-jose[cryptography] | 3.3.0 | (missing) | Future | Add when integrating Cognito |
| pyjwt | 2.10.1 | (missing) | Future | Add when integrating Cognito |
| passlib[bcrypt] | 1.7.4 | (missing) | Future | Add when integrating Cognito |
| **Task queue (future)** | | | | |
| celery | 5.4.0 | (missing) | Future | Add when replacing thread runner |
| redis | >=5.0.1 | (missing) | Future | Add when integrating Celery |
| **HTTP** | | | | |
| httpx | 0.28.1 | >=0.27 | Compatible | Match to 0.28.1 |
| requests | (missing) | >=2.32 | **YES** — they don't use it | Keep for now (Playwright deps); evaluate removing later |
| **Utilities** | | | | |
| python-multipart | 0.0.9 | >=0.0.9 | Compatible | Match to 0.0.9 |
| python-dotenv | 1.0.1 | (missing) | Future | Add when .env.local workflow needed |
| boto3 | 1.34.162 | (missing) | Future | Add when S3 backend is real (not dev) |
| **Playwright** | | | | |
| playwright | (missing) | >=1.40 | **OURS ONLY** | Keep — parent doesn't have clerk scraper |
| pillow | (missing) | >=11.0 | **OURS ONLY** | Keep — flood map compositing |
| **Dev** | | | | |
| pytest | 7.4.4 | >=8.0 | **YES** — we're NEWER | Match to 7.4.4 or keep 8.0 if they're upgrading |
| ruff | 0.4.4 | (missing) | Future | Add |
| mypy | 1.10.0 | (missing) | Future | Add |
| pytest-asyncio | 0.23.6 | (missing) | Future | Add (they use async tests) |

---

## Architecture patterns to adopt from parent

### 1. Module structure (match their convention)
```
app/modules/research/
  __init__.py
  models.py         ← our QP models (Order, EvidenceDocument, etc.)
  repository.py     ← DB queries (replace raw SQLAlchemy with repository pattern)
  router.py         ← FastAPI routes (/api/v2/research/*)
  service.py        ← business logic (our orchestrator.run_research wrapper)
  tasks.py          ← Celery tasks (replaces thread runner)
  state_machine.py  ← job lifecycle transitions
  events.py         ← domain events (research.started, document.locked)
  utils.py          ← helpers
```

### 2. DB pattern (match their convention)
```
app/db/
  base.py           ← declarative Base + configure_versioning()
  models.py         ← import all module models here
  migrations/
    env.py          ← loads DATABASE_URL from .env
    versions/       ← Alembic migrations (they have 31)
```

### 3. Config pattern (match their convention)
```python
# app/core/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./test.db"
    S3_ARTIFACTS_BUCKET: str = ""
    COGNITO_USER_POOL_ID: str = ""
    # ... etc
    class Config:
        env_file = ".env.local"
```

### 4. Auth pattern (future — when we integrate)
```python
# app/core/deps.py
from fastapi import Depends, HTTPException
from app.core.auth import verify_cognito_token

async def get_current_user(token = Depends(verify_cognito_token)):
    return token
```

### 5. Test structure (match their convention)
```
tests/
  unit/           ← fast, no DB (like our test_parcel.py, test_contract_conformance.py)
  isolation/      ← with DB but no network (like our test_quickplot_api.py)
  integration/    ← real DB + network (like our test_quickplot_ui.py)
```

---

## Immediate action: update requirements.txt

Pin to match parent's versions for shared libraries. Keep our unique deps (playwright, pillow).

```
# --- Core (match mapperty/quickplot-api pyproject.toml) ---
fastapi==0.111.0
uvicorn[standard]==0.30.0
pydantic==2.10.0
pydantic-settings==2.3.4
python-multipart==0.0.9

# --- Database (match parent) ---
sqlalchemy==2.0.46
alembic==1.13.2
psycopg2-binary==2.9.10
psycopg[binary]>=3.2.0

# --- HTTP ---
httpx==0.28.1
requests>=2.32            # us only (Playwright deps)

# --- Ours only (parent doesn't use these) ---
pillow>=11.0              # flood map compositing
playwright>=1.40          # clerk deed/plat scraper

# --- test only ---
pytest>=8.0
httpx>=0.27               # fastapi.testclient transport
```

---

## What NOT to change yet

| Library | Why wait |
|---------|----------|
| celery / redis | We don't have Redis locally — add when deploying to AWS |
| boto3 | We use local FS in dev — add when S3 backend is real |
| python-jose / passlib | Auth is deferred — no Cognito in local dev |
| ruff / mypy | Add when we have CI (no point linting locally without enforcement) |
| langchain / opentelemetry | AI + observability — future feature, not core engine |

---

## Timeline

| When | What |
|------|------|
| **Now** | Pin shared library versions in requirements.txt |
| **Now** | Add alembic + alembic.ini scaffold |
| **Day 2–3** | Structure app/modules/research/ to match parent's module pattern |
| **Week 2** | Add Celery + Redis when we have a staging environment |
| **Integration** | Branch fixed/layer_architecture, drop our code into their module structure |

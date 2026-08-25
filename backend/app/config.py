"""Central configuration."""
import os
import pathlib

# Where fetched job research folders are written.
# Default: a "jobs" folder next to the backend. Override with SURVEY_JOBS_DIR.
JOBS_DIR = pathlib.Path(
    os.environ.get(
        "SURVEY_JOBS_DIR",
        pathlib.Path(__file__).resolve().parents[2] / "jobs",
    )
).resolve()
JOBS_DIR.mkdir(parents=True, exist_ok=True)

# Evidence Locker — curated documents a researcher sends downstream for an order, keyed by
# order number. Sibling of jobs/. Override with SURVEY_EVIDENCE_DIR.
EVIDENCE_DIR = pathlib.Path(
    os.environ.get(
        "SURVEY_EVIDENCE_DIR",
        pathlib.Path(__file__).resolve().parents[2] / "evidence",
    )
).resolve()
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

# Frontend location
FRONTEND_DIR = (pathlib.Path(__file__).resolve().parents[2] / "frontend").resolve()


# Database / index. Mirrors the survey-automation pattern: build a Postgres URL from
# POSTGRES_* when present (URL-quoting the credentials), else honour an explicit DATABASE_URL,
# else default to a local SQLite file — so the same code runs SQLite in dev / Postgres in prod.
def _build_database_url() -> str:
    from urllib.parse import quote_plus
    user = os.environ.get("POSTGRES_USER", "").strip()
    password = os.environ.get("POSTGRES_PASSWORD", "").strip()
    host = os.environ.get("POSTGRES_HOST", "db").strip()
    db = os.environ.get("POSTGRES_DB", "").strip()
    if user and password and db:
        return f"postgresql+psycopg2://{quote_plus(user)}:{quote_plus(password)}@{host}/{db}"
    default_sqlite = (JOBS_DIR.parent / "survey_research.db").as_posix()
    return os.environ.get("DATABASE_URL", f"sqlite:///{default_sqlite}")


DATABASE_URL = _build_database_url()

HTTP_TIMEOUT = 30
# Browser-like UA: some county GIS servers (e.g. Johnson County IA) 403 any non-browser
# User-Agent. A browser string is the safe default for hitting public gov ArcGIS endpoints and
# matches what check_url() already sends.
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

APP_NAME = "Survey Research Automation"

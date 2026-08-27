import sys
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# -------------------------------
# ADD PROJECT PATH
# -------------------------------
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "app"))

# -------------------------------
# LOAD ENV VARIABLES
# -------------------------------
from dotenv import load_dotenv

load_dotenv()

# -------------------------------
# ALEMBIC CONFIG
# -------------------------------
config = context.config

# SAFE DATABASE URL (No Pydantic dependency)
database_url = os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/researchhub")
config.set_main_option("sqlalchemy.url", database_url)

# -------------------------------
# LOGGING CONFIG
# -------------------------------
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# -------------------------------
# IMPORT DB + MODELS
# -------------------------------
from app.db.base import Base  # noqa: E402
import app.engine.models  # noqa: E402,F401  (register tables)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
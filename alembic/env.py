import os
from logging.config import fileConfig

from dotenv import load_dotenv
from sqlalchemy import create_engine

from alembic import context
from shared.db import Base, get_engine
import shared.models  # noqa: F401 — registers all models with Base.metadata

load_dotenv()

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = os.environ["DATABASE_URL"]
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _override_url() -> str | None:
    """A connection URL supplied by the caller instead of `DATABASE_URL`.

    `get_engine()` reads `DATABASE_URL` through a cached settings object, so a
    caller wanting a different database — the integration suite migrating its own
    test database — cannot get there by passing a URL. Both forms are accepted:

        uv run alembic -x db_url=postgresql://…/overklagan_test upgrade head
        config.attributes["db_url"] = "…"   # programmatic, from a fixture
    """
    from_attributes = config.attributes.get("db_url")
    if from_attributes:
        return str(from_attributes)
    return context.get_x_argument(as_dictionary=True).get("db_url")


def run_migrations_online() -> None:
    url = _override_url()
    engine = create_engine(url) if url else get_engine()
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

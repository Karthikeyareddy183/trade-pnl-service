"""Create the PostgreSQL database named in DATABASE_URL if it does not exist yet.

Usage: ``python -m app.db.create_database`` (no ``psql`` on PATH needed), then
``alembic upgrade head`` to create the tables.
"""

import sqlalchemy as sa

from app.config import get_settings, to_sync_url


def ensure_database(sync_url: sa.URL) -> bool:
    """Create ``sync_url.database`` if missing. Returns True when it was created."""
    admin = sa.create_engine(
        sync_url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 3},
    )
    try:
        with admin.connect() as conn:
            exists = conn.scalar(
                sa.text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": sync_url.database},
            )
            if exists:
                return False
            conn.execute(sa.text(f'CREATE DATABASE "{sync_url.database}"'))
            return True
    finally:
        admin.dispose()


def main() -> None:
    url = sa.make_url(to_sync_url(get_settings().database_url))
    created = ensure_database(url)
    print(f"Database '{url.database}' {'created' if created else 'already exists'}.")


if __name__ == "__main__":
    main()

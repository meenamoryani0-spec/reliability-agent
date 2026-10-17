"""Explicit upgrade/status commands. No migration runs during application startup."""

import argparse

from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.db.database import create_storage_engine
from app.db.migrate import HEAD, current_revision, upgrade


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("upgrade", "status"))
    arguments = parser.parse_args()
    engine = None
    try:
        engine = create_storage_engine(Settings())
        if engine is None:
            print("NOT_CONFIGURED: select local or PostgreSQL application storage")
            return 1
        if arguments.action == "upgrade":
            upgrade(engine)
        revision = current_revision(engine)
        print("READY: " + HEAD if revision == HEAD else "MIGRATION_REQUIRED")
        return 0 if revision == HEAD else 1
    except (ValueError, SQLAlchemyError):
        print("NOT_VERIFIED: application database operation failed")
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())

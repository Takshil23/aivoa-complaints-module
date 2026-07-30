"""Create the `aivoa` database (and optionally its role) on a fresh server.

SQLAlchemy will create the *tables* but never the database itself, and a fresh
PostgreSQL or MySQL install has neither. This does that one step, over the
driver rather than the `psql` / `mysql` CLI — neither of which is on PATH after a
default Windows install.

PostgreSQL, using the superuser chosen during setup:

    .venv\\Scripts\\python.exe scripts/create_db.py \\
        --admin postgresql+psycopg://postgres:YOURPASSWORD@localhost:5432/postgres

MySQL:

    .venv\\Scripts\\python.exe scripts/create_db.py \\
        --admin mysql+pymysql://root:YOURPASSWORD@localhost:3306/mysql

Prints the DATABASE_URL to put in backend/.env, then verify with:

    .venv\\Scripts\\python.exe scripts/verify_db.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import quote_plus

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, text  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admin", required=True, help="admin/superuser URL")
    parser.add_argument("--db", default="aivoa", help="database to create")
    parser.add_argument(
        "--app-user",
        default="",
        help="optional non-superuser role to create and grant (recommended)",
    )
    parser.add_argument("--app-password", default="aivoa")
    args = parser.parse_args()

    admin_url = args.admin
    dialect = admin_url.split(":", 1)[0]
    is_postgres = dialect.startswith("postgresql")

    try:
        # CREATE DATABASE cannot run inside a transaction on PostgreSQL.
        engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        with engine.connect() as connection:
            if is_postgres:
                exists = connection.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :name"),
                    {"name": args.db},
                ).scalar()
            else:
                exists = connection.execute(
                    text(
                        "SELECT 1 FROM information_schema.schemata "
                        "WHERE schema_name = :name"
                    ),
                    {"name": args.db},
                ).scalar()

            if exists:
                print(f"database '{args.db}' already exists — leaving it alone")
            else:
                connection.execute(text(f'CREATE DATABASE "{args.db}"'))
                print(f"created database '{args.db}'")

            if args.app_user:
                if is_postgres:
                    has_role = connection.execute(
                        text("SELECT 1 FROM pg_roles WHERE rolname = :name"),
                        {"name": args.app_user},
                    ).scalar()
                    if not has_role:
                        connection.execute(
                            text(
                                f'CREATE ROLE "{args.app_user}" LOGIN PASSWORD '
                                f"'{args.app_password}'"
                            )
                        )
                        print(f"created role '{args.app_user}'")
                    connection.execute(
                        text(
                            f'GRANT ALL PRIVILEGES ON DATABASE "{args.db}" '
                            f'TO "{args.app_user}"'
                        )
                    )
                else:
                    connection.execute(
                        text(
                            f"CREATE USER IF NOT EXISTS '{args.app_user}'@'%' "
                            f"IDENTIFIED BY '{args.app_password}'"
                        )
                    )
                    connection.execute(
                        text(
                            f"GRANT ALL PRIVILEGES ON `{args.db}`.* "
                            f"TO '{args.app_user}'@'%'"
                        )
                    )
                print(f"granted '{args.app_user}' full rights on '{args.db}'")

                if is_postgres:
                    # On PG15+ the public schema is not writable by default.
                    owner_engine = create_engine(
                        _swap_database(admin_url, args.db),
                        isolation_level="AUTOCOMMIT",
                    )
                    with owner_engine.connect() as db_conn:
                        db_conn.execute(
                            text(
                                f'GRANT ALL ON SCHEMA public TO "{args.app_user}"'
                            )
                        )
                    owner_engine.dispose()
                    print("granted schema rights (PostgreSQL 15+ needs this)")
        engine.dispose()
    except Exception as exc:  # noqa: BLE001
        print(f"\nFailed: {exc}\n")
        print(
            "Check that the server is running and the admin password is right.\n"
            "On Windows the PostgreSQL service is 'postgresql-x64-<version>'."
        )
        return 1

    if args.app_user:
        password = quote_plus(args.app_password)
        host = admin_url.rsplit("@", 1)[-1].rsplit("/", 1)[0]
        url = f"{dialect}://{args.app_user}:{password}@{host}/{args.db}"
    else:
        url = _swap_database(admin_url, args.db)

    print("\nPut this in backend/.env:\n")
    print(f"  DATABASE_URL={url}\n")
    print("Then:  .venv\\Scripts\\python.exe scripts/verify_db.py")
    return 0


def _swap_database(url: str, database: str) -> str:
    head, _, _tail = url.rpartition("/")
    return f"{head}/{database}"


if __name__ == "__main__":
    raise SystemExit(main())

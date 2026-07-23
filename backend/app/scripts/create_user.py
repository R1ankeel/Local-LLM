from __future__ import annotations

import argparse

from app.db import get_db, init_db
from app.routers.auth import create_user


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a local user")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args()

    init_db()
    db_session = next(get_db())
    try:
        user = create_user(db_session, args.username, args.password)
    finally:
        db_session.close()
    print(f"Created user: {user.username} (id={user.id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

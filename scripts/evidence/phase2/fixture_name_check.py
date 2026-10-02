"""Preview or read-only check the isolated fixture database name."""

from __future__ import annotations

import argparse
import tomllib
from pathlib import Path

from scripts.fixtures.phase2_fixture_namespace import TEST_DATABASE


def admin_params(config_path: Path) -> dict[str, str]:
    """Load only the existing admin profile; never print its password."""
    profile = tomllib.loads(config_path.read_text(encoding="utf-8"))["connections"][
        "quakewatch_admin"
    ]
    if profile.get("role") != "ACCOUNTADMIN":
        raise ValueError("quakewatch_admin profile must use ACCOUNTADMIN")
    required = ("account", "user", "password")
    if any(not isinstance(profile.get(name), str) or not profile[name] for name in required):
        raise ValueError("quakewatch_admin profile lacks account, user, or password")
    return {name: profile[name] for name in (*required, "role")}


def name_occupied(cursor) -> bool:
    """Check an exact name with the caller's existing admin connection."""
    cursor.execute(f"SHOW DATABASES LIKE '{TEST_DATABASE}'")
    columns = [column[0].lower() for column in cursor.description]
    name_index = columns.index("name")
    names = {str(row[name_index]).upper() for row in cursor.fetchall()}
    return TEST_DATABASE in names


def check_name(config_path: Path) -> bool:
    """Return True if the exact fixture database name is already present."""
    import snowflake.connector

    with snowflake.connector.connect(**admin_params(config_path)) as connection:
        with connection.cursor() as cursor:
            return name_occupied(cursor)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="connect for one metadata-only SHOW")
    args = parser.parse_args()
    if not args.execute:
        print("Phase 2 fixture name: preview only; no Snowflake connection")
        print(f"Admin metadata check: SHOW DATABASES LIKE '{TEST_DATABASE}'")
        print("Only an exact name match blocks setup; LIKE underscores may match other names")
        return
    occupied = check_name(Path.home() / ".snowflake" / "config.toml")
    print(
        f"Fixture database name: {'occupied; stop and inspect' if occupied else 'available for setup review'}"
    )


if __name__ == "__main__":
    main()

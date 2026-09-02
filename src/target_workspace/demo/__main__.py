"""`python -m target_workspace.demo` — CLI to list and seed scenarios.

Usage:
    python -m target_workspace.demo list
    python -m target_workspace.demo seed --scenario tf-dagger-f3ead
    python -m target_workspace.demo seed --scenario tf-dagger-f3ead \\
        --database-url sqlite:///./tw.db
"""

from __future__ import annotations

import argparse
import sys

from target_workspace.api.config import get_settings
from target_workspace.db import init_db
from target_workspace.demo.loader import (
    ScenarioNotFoundError,
    discover_scenarios,
    seed_workspace,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m target_workspace.demo")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("list", help="List bundled scenarios")

    seed = sub.add_parser("seed", help="Seed a scenario into the DB")
    seed.add_argument(
        "--scenario",
        required=True,
        help="Scenario id (file stem under demo/scenarios/)",
    )
    seed.add_argument(
        "--database-url",
        default=None,
        help="DB URL override; defaults to TW_DATABASE_URL or sqlite:///./tw.db",
    )

    args = parser.parse_args(argv)
    if args.cmd in (None, "list"):
        scenarios = discover_scenarios()
        if not scenarios:
            print("(no scenarios bundled)")
            return 0
        print("Bundled scenarios:")
        for sid, s in scenarios.items():
            print(f"  {sid:30}  {s.name}")
        return 0

    if args.cmd == "seed":
        settings = get_settings()
        db_url = args.database_url or settings.database_url
        engine = init_db(db_url)
        try:
            result = seed_workspace(engine, scenario_id=args.scenario)
        except ScenarioNotFoundError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2
        print(result)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())

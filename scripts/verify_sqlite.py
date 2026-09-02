"""Fail the container build if the bundled SQLite is older than the CVE baseline.

CVE-2025-6965 was fixed in SQLite 3.50.2. Python interpreters bundle whichever
SQLite was current at the time of their release; Chainguard's hardened Python
images stay current but a hostile or stale base image could ship an older
version. This script runs during `docker build` and aborts the build if the
bundled sqlite3 module is below the threshold.

Threshold: SQLite >= 3.50.2.
"""

from __future__ import annotations

import sqlite3
import sys

MIN_SQLITE = (3, 50, 2)


def main() -> int:
    parts = tuple(int(p) for p in sqlite3.sqlite_version.split("."))
    if parts < MIN_SQLITE:
        threshold = ".".join(str(p) for p in MIN_SQLITE)
        msg = (
            f"FAIL: bundled SQLite {sqlite3.sqlite_version} < required {threshold}. "
            f"Reference: https://www.sqlite.org/cves.html (CVE-2025-6965). "
            f"Rebuild the base image with a current SQLite."
        )
        print(msg, file=sys.stderr)
        return 1
    print(f"OK: bundled SQLite {sqlite3.sqlite_version} >= 3.50.2")
    return 0


if __name__ == "__main__":
    sys.exit(main())

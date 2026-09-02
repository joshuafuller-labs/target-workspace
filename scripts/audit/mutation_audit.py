#!/usr/bin/env python3
"""Manual mutation audit — TDD step 2.

For each (target_module, test_file, list[mutation]) entry, apply each
mutation in-place, run the test file, restore. A mutation is KILLED
if any test fails after the mutation is applied (= the test suite
catches the bug). A mutation that SURVIVES means the test suite has
a gap — either write a new test that catches it, or document why the
mutation isn't behavior-relevant.

Mutations are written by hand so they target real semantics, not
synthetic line-flip noise. Each entry pairs a (find_str, replace_str)
patch with a short description.

Usage:  scripts/audit/mutation_audit.py [module_name]
Exit:   0 if mutation kill rate >= MIN_KILL_RATE for all modules
        1 otherwise — survivors listed
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MIN_KILL_RATE = 0.80


@dataclass(frozen=True)
class Mutation:
    description: str
    find: str
    replace: str


@dataclass(frozen=True)
class ModuleAudit:
    name: str
    src: Path
    tests: tuple[Path, ...]
    mutations: tuple[Mutation, ...]


# ──────────────────────────────────────────────────────────────────────
# Audit set. Hand-curated to exercise the actual decision points the
# tests are supposed to cover. Each mutation either FLIPS the policy
# (e.g. roles compare wrong way) or REMOVES the check entirely.
# ──────────────────────────────────────────────────────────────────────

AUDIT: tuple[ModuleAudit, ...] = (
    ModuleAudit(
        name="rbac",
        src=REPO / "src/target_workspace/api/rbac.py",
        tests=(REPO / "tests/integration/test_rbac.py",),
        mutations=(
            Mutation(
                "tier order reversed (admin becomes least-privileged)",
                '_TIERS: Final[tuple[str, ...]] = (\n    "viewer",\n    "observer",\n    "operator",\n    "approver",\n    "commander",\n    "admin",\n)',
                '_TIERS: Final[tuple[str, ...]] = (\n    "admin",\n    "commander",\n    "approver",\n    "operator",\n    "observer",\n    "viewer",\n)',
            ),
            Mutation(
                "has_role always True (no role enforcement)",
                "return role_rank(user_role) >= role_rank(required)",
                "return True",
            ),
            Mutation(
                "has_role always False (everything blocked)",
                "return role_rank(user_role) >= role_rank(required)",
                "return False",
            ),
            Mutation(
                "require_role short-circuits (gate removed)",
                "if has_role(user_role, required):\n        return",
                "if True:\n        return",
            ),
            Mutation(
                "role_rank floor flipped (unknown → max privilege)",
                "return _TIER_INDEX.get(role, 0)",
                "return _TIER_INDEX.get(role, 99)",
            ),
        ),
    ),
    ModuleAudit(
        name="track_correlation",
        src=REPO / "src/target_workspace/db/track_correlation.py",
        tests=(REPO / "tests/integration/test_track_correlation.py",),
        mutations=(
            Mutation(
                "DEFAULT_TOL_METERS = 0 (no observation ever correlates)",
                "DEFAULT_TOL_METERS = 500.0",
                "DEFAULT_TOL_METERS = 0.0",
            ),
            Mutation(
                "DEFAULT_TOL_METERS = infinity (everything correlates)",
                "DEFAULT_TOL_METERS = 500.0",
                "DEFAULT_TOL_METERS = 1.0e12",
            ),
            Mutation(
                "haversine returns 0 (distance never matters)",
                "return 2 * radius_earth_m * math.asin(math.sqrt(a))",
                "return 0.0",
            ),
            Mutation(
                "affiliation check flipped (mismatch correlates)",
                "if affiliation_of(row.cot_type) != candidate_aff:",
                "if affiliation_of(row.cot_type) == candidate_aff:",
            ),
            Mutation(
                "horizon bypassed (any age correlates)",
                "if observed < horizon:",
                "if False:",
            ),
        ),
    ),
    ModuleAudit(
        name="repositories",
        src=REPO / "src/target_workspace/db/repositories.py",
        tests=(REPO / "tests/integration/test_reorder.py",),
        mutations=(
            Mutation(
                "after_id=None inserts at BOTTOM, not top (semantics inverted)",
                "first_pos = siblings[0].position if siblings else 1.0\n        new_pos = first_pos - 1.0",
                "first_pos = siblings[-1].position if siblings else 1.0\n        new_pos = first_pos + 1.0",
            ),
            Mutation(
                "midpoint calculation reversed (off-by-one in same direction every drag)",
                "new_pos = (anchor.position + next_sibling.position) / 2.0",
                "new_pos = anchor.position + next_sibling.position",
            ),
            Mutation(
                "anchor-not-found returns target unchanged instead of None (404 path broken)",
                "if anchor_index is None:\n            return None",
                "if anchor_index is None:\n            return row",
            ),
            Mutation(
                "list_targets_in_column drops ORDER BY position (reorder invisible)",
                "def list_targets_in_column(session: Session, column_id: UUID) -> list[Target]:\n    rows = session.exec(\n        select(TargetTable)\n        .where(TargetTable.column_id == column_id)\n        .order_by(TargetTable.position, TargetTable.created_at),  # type: ignore[arg-type]\n    ).all()",
                "def list_targets_in_column(session: Session, column_id: UUID) -> list[Target]:\n    rows = session.exec(\n        select(TargetTable)\n        .where(TargetTable.column_id == column_id),\n    ).all()",
            ),
            Mutation(
                "create_target ignores _next_position_in_column (all rows pile up at top)",
                "position=_next_position_in_column(session, column_id),",
                "position=0.0,",
            ),
        ),
    ),
    ModuleAudit(
        name="routers_targets",
        src=REPO / "src/target_workspace/api/routers/targets.py",
        tests=(
            REPO / "tests/integration/test_reorder.py",
            REPO / "tests/integration/test_rbac.py",
        ),
        mutations=(
            Mutation(
                "create_target skips RBAC require_role (anyone can create)",
                'require_role(user.role, "observer", action="create target")',
                "pass  # mutated: rbac skipped",
            ),
            Mutation(
                "reorder skips RBAC require_role (anyone can reorder)",
                'require_role(user.role, "operator", action="reorder target")',
                "pass  # mutated: rbac skipped",
            ),
            Mutation(
                "reorder returns 200 on missing row (silent 404 → 200)",
                'if row is None:\n        raise HTTPException(\n            status_code=status.HTTP_404_NOT_FOUND,\n            detail="target or anchor not found in column",\n        )',
                "if row is None:\n        pass  # mutated: missing now returns 200",
            ),
            Mutation(
                "approval-gate skipped (operator can move into gated columns)",
                'if dest is not None and dest.requires_approval and not has_role(user.role, "approver"):',
                "if False:",
            ),
        ),
    ),
    ModuleAudit(
        name="tak_server_publisher",
        src=REPO / "src/target_workspace/plugins/publishers/tak_server.py",
        tests=(REPO / "tests/unit/test_publishers_tak_server.py",),
        mutations=(
            Mutation(
                "host validation skipped (silently sends to '' which would fail differently)",
                'if not host:\n            msg = "tak_server publisher requires `host` in adapter_config"\n            raise ValueError(msg)',
                "if False:\n            raise ValueError('unused')",
            ),
            Mutation(
                "cert path validation skipped (silently sends to TLS handshake without certs)",
                'if not cert_path or not key_path:\n            msg = (\n                "tak_server publisher requires `client_cert_pem_path` and "\n                "`client_key_pem_path` for mTLS client authentication"\n            )\n            raise ValueError(msg)',
                "if False:",
            ),
            Mutation(
                "hostname verification disabled by default (security regression)",
                'verify_hostname = bool(adapter_config.get("verify_hostname", True))',
                'verify_hostname = bool(adapter_config.get("verify_hostname", False))',
            ),
            Mutation(
                "TLS cert verification mode dropped to CERT_NONE",
                "ctx.verify_mode = ssl.CERT_REQUIRED",
                "ctx.verify_mode = ssl.CERT_NONE",
            ),
            Mutation(
                "CoT payload sent without newline framing (TAK Server may not parse)",
                'tls.sendall(payload + b"\\n")',
                "tls.sendall(payload)",
            ),
        ),
    ),
)


def find_audit(name: str | None) -> Sequence[ModuleAudit]:
    if name is None:
        return AUDIT
    matches = [a for a in AUDIT if a.name == name]
    if not matches:
        print(f"no audit named {name!r}", file=sys.stderr)
        sys.exit(2)
    return matches


def apply_mutation(src: Path, mutation: Mutation) -> None:
    text = src.read_text()
    if mutation.find not in text:
        raise AssertionError(
            f"mutation find-string not present in {src.name}:\n  {mutation.find!r}"
        )
    if text.count(mutation.find) > 1:
        raise AssertionError(
            f"mutation find-string is ambiguous (matches >1 location) in {src.name}"
        )
    src.write_text(text.replace(mutation.find, mutation.replace))


def run_tests(test_files: tuple[Path, ...]) -> bool:
    """Returns True if every test PASSED, False if any failed/errored."""
    cmd = [
        ".venv/bin/python",
        "-m",
        "pytest",
        *(str(p.relative_to(REPO)) for p in test_files),
        "-x",
        "--no-cov",
        "-q",
        "-p",
        "no:cacheprovider",
        "-o",
        "addopts=",
    ]
    rc = subprocess.run(cmd, cwd=REPO, capture_output=True).returncode
    return rc == 0


def audit_module(audit: ModuleAudit) -> tuple[int, int, list[Mutation]]:
    """Returns (killed, total, survivors)."""
    backup = audit.src.with_suffix(audit.src.suffix + ".bak")
    shutil.copy(audit.src, backup)
    killed = 0
    survivors: list[Mutation] = []
    try:
        for m in audit.mutations:
            # Restore from backup before each mutation.
            shutil.copy(backup, audit.src)
            apply_mutation(audit.src, m)
            passed = run_tests(audit.tests)
            shutil.copy(backup, audit.src)  # restore immediately
            if passed:
                # Mutation SURVIVED — tests didn't catch it. Gap.
                survivors.append(m)
                status = "✗ SURVIVED"
            else:
                killed += 1
                status = "✓ killed"
            print(f"  {status:<14}  {m.description}")
    finally:
        shutil.move(str(backup), audit.src)
    return killed, len(audit.mutations), survivors


def main(argv: list[str] | None = None) -> int:
    # Accept an explicit argv so in-process callers (e.g. the pytest wrapper)
    # don't inherit pytest's own sys.argv flags. CLI use falls back to argv.
    args = sys.argv[1:] if argv is None else argv
    target = args[0] if args else None
    audits = find_audit(target)
    all_pass = True
    print()
    for a in audits:
        print("════════════════════════════════════════════════════════════════")
        print(f"AUDIT: {a.name}  ({a.src.relative_to(REPO)})")
        print(f"  tests: {', '.join(str(p.relative_to(REPO)) for p in a.tests)}")
        print()
        killed, total, survivors = audit_module(a)
        rate = killed / total
        print()
        print(f"  kill rate: {killed}/{total} = {rate:.0%}")
        if rate < MIN_KILL_RATE:
            all_pass = False
            print(f"  ✗ BELOW threshold ({MIN_KILL_RATE:.0%}) — survivors:")
            for m in survivors:
                print(f"      - {m.description}")
        else:
            print(f"  ✓ at/above threshold ({MIN_KILL_RATE:.0%})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())

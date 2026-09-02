from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).resolve().parents[2]
NIGHTLY_WORKFLOW = ROOT / ".github" / "workflows" / "nightly.yml"


def _nightly_job(job_name: str) -> dict[str, Any]:
    workflow = cast(dict[str, Any], yaml.safe_load(NIGHTLY_WORKFLOW.read_text()))
    jobs = cast(dict[str, Any], workflow["jobs"])
    return cast(dict[str, Any], jobs[job_name])


def test_scorecard_has_private_repo_read_permissions() -> None:
    scorecard = _nightly_job("scorecard")
    permissions = cast(dict[str, str], scorecard["permissions"])

    assert permissions["contents"] == "read"
    assert permissions["issues"] == "read"
    assert permissions["pull-requests"] == "read"
    assert permissions["checks"] == "read"
    assert permissions["security-events"] == "write"
    assert permissions["id-token"] == "write"

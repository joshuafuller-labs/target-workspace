from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).resolve().parents[2]
PRECOMMIT_CONFIG = ROOT / ".pre-commit-config.yaml"


def _config() -> dict[str, Any]:
    return cast(dict[str, Any], yaml.safe_load(PRECOMMIT_CONFIG.read_text()))


def _hooks_by_id() -> dict[str, dict[str, Any]]:
    hooks: dict[str, dict[str, Any]] = {}
    for repo in cast(list[dict[str, Any]], _config()["repos"]):
        for hook in cast(list[dict[str, Any]], repo["hooks"]):
            hooks[cast(str, hook["id"])] = hook
    return hooks


def test_pre_push_hooks_are_not_installed_by_default() -> None:
    config = _config()

    assert config["default_install_hook_types"] == ["pre-commit", "commit-msg"]
    assert config["default_stages"] == ["pre-commit"]


def test_mypy_hook_runs_in_project_uv_environment() -> None:
    hook = _hooks_by_id()["mypy"]

    assert hook["language"] == "system"
    assert hook["entry"] == "env MYPYPATH=src uv run mypy"
    assert "additional_dependencies" not in hook


def test_full_pytest_suite_is_manual_not_pre_push() -> None:
    hook = _hooks_by_id()["pytest-manual"]

    assert hook["entry"] == 'uv run pytest -m "not slow" --no-cov -n auto -q'
    assert hook["stages"] == ["manual"]

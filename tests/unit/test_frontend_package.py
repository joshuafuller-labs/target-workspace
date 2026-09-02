from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_frontend_lint_script_has_eslint_tooling() -> None:
    package = json.loads((ROOT / "frontend" / "package.json").read_text())
    dev_dependencies = package["devDependencies"]

    assert "eslint ." in package["scripts"]["lint"]
    assert "eslint" in dev_dependencies
    assert "typescript-eslint" in dev_dependencies
    assert "@eslint/js" in dev_dependencies
    assert (ROOT / "frontend" / "eslint.config.js").exists()

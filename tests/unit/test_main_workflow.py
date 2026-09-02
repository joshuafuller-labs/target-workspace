from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).resolve().parents[2]
MAIN_WORKFLOW = ROOT / ".github" / "workflows" / "main.yml"
PR_WORKFLOW = ROOT / ".github" / "workflows" / "pr.yml"
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
SEMGREP_WORKFLOW = ROOT / ".github" / "workflows" / "semgrep.yml"
PYPROJECT = ROOT / "pyproject.toml"


def _workflow(workflow_path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], yaml.safe_load(workflow_path.read_text()))


def _workflow_triggers(workflow: dict[str, Any]) -> dict[str, Any]:
    # PyYAML's YAML 1.1 loader treats the key `on` as boolean True.
    return cast(dict[str, Any], cast(dict[Any, Any], workflow)[True])


def _workflow_steps(workflow_path: Path, job_name: str) -> list[dict[str, Any]]:
    workflow = _workflow(workflow_path)
    jobs = cast(dict[str, Any], workflow["jobs"])
    publish = cast(dict[str, Any], jobs[job_name])
    return cast(list[dict[str, Any]], publish["steps"])


def _publish_steps() -> list[dict[str, Any]]:
    return _workflow_steps(MAIN_WORKFLOW, "publish")


def _release_publish_steps() -> list[dict[str, Any]]:
    return _workflow_steps(RELEASE_WORKFLOW, "publish")


def _pr_python_pytest_step() -> dict[str, Any]:
    workflow = _workflow(PR_WORKFLOW)
    jobs = cast(dict[str, Any], workflow["jobs"])
    python = cast(dict[str, Any], jobs["python"])
    steps = cast(list[dict[str, Any]], python["steps"])
    return next(step for step in steps if step["name"] == "Pytest (parallel + coverage)")


def _pr_python_step(step_name: str) -> dict[str, Any]:
    workflow = _workflow(PR_WORKFLOW)
    jobs = cast(dict[str, Any], workflow["jobs"])
    python = cast(dict[str, Any], jobs["python"])
    steps = cast(list[dict[str, Any]], python["steps"])
    return next(step for step in steps if step["name"] == step_name)


def _pr_frontend_steps() -> list[dict[str, Any]]:
    workflow = _workflow(PR_WORKFLOW)
    jobs = cast(dict[str, Any], workflow["jobs"])
    frontend = cast(dict[str, Any], jobs["frontend"])
    return cast(list[dict[str, Any]], frontend["steps"])


def _pr_container_steps() -> list[dict[str, Any]]:
    workflow = _workflow(PR_WORKFLOW)
    jobs = cast(dict[str, Any], workflow["jobs"])
    container = cast(dict[str, Any], jobs["container"])
    return cast(list[dict[str, Any]], container["steps"])


def _pr_container_job() -> dict[str, Any]:
    workflow = _workflow(PR_WORKFLOW)
    jobs = cast(dict[str, Any], workflow["jobs"])
    return cast(dict[str, Any], jobs["container"])


def _pr_postgres_migrations_job() -> dict[str, Any]:
    workflow = _workflow(PR_WORKFLOW)
    jobs = cast(dict[str, Any], workflow["jobs"])
    return cast(dict[str, Any], jobs["postgres-migrations"])


def _pr_playwright_job() -> dict[str, Any]:
    workflow = _workflow(PR_WORKFLOW)
    jobs = cast(dict[str, Any], workflow["jobs"])
    return cast(dict[str, Any], jobs["playwright"])


def test_main_workflow_installs_cosign_without_envsubst_dependent_action() -> None:
    install_steps = [
        next(step for step in _publish_steps() if step["name"] == "Install cosign"),
        next(step for step in _release_publish_steps() if step["name"] == "Install cosign"),
    ]

    for install_step in install_steps:
        assert "uses" not in install_step
        run_script = cast(str, install_step["run"])
        assert "sigstore/cosign-installer" not in run_script
        assert "envsubst" not in run_script


def test_main_workflow_verifies_pinned_cosign_binary() -> None:
    install_steps = [
        next(step for step in _publish_steps() if step["name"] == "Install cosign"),
        next(step for step in _release_publish_steps() if step["name"] == "Install cosign"),
    ]

    for install_step in install_steps:
        env = cast(dict[str, str], install_step["env"])
        run_script = cast(str, install_step["run"])

        assert env["COSIGN_VERSION"] == "v3.0.6"
        assert (
            env["COSIGN_LINUX_AMD64_SHA256"]
            == "c956e5dfcac53d52bcf058360d579472f0c1d2d9b69f55209e256fe7783f4c74"  # pragma: allowlist secret
        )
        assert "sha256sum --check -" in run_script
        assert 'echo "$RUNNER_TEMP/cosign" >> "$GITHUB_PATH"' in run_script


def test_image_publish_retries_ghcr_login_without_login_action() -> None:
    login_steps = [
        next(step for step in _publish_steps() if step["name"] == "Login to GHCR"),
        next(step for step in _release_publish_steps() if step["name"] == "Login to GHCR"),
    ]

    for login_step in login_steps:
        assert "uses" not in login_step
        run_script = cast(str, login_step["run"])
        assert "docker/login-action" not in run_script
        assert "docker login ghcr.io" in run_script
        assert "--password-stdin" in run_script
        assert "for attempt in 1 2 3 4 5" in run_script
        assert "sleep $((attempt * 5))" in run_script


def test_publish_workflows_use_buildx_registry_attestations() -> None:
    workflow_jobs = [
        (_workflow_steps(MAIN_WORKFLOW, "publish"), "Build + push (multi-arch)"),
        (_workflow_steps(RELEASE_WORKFLOW, "publish"), "Build + push versioned (multi-arch)"),
    ]

    for steps, step_name in workflow_jobs:
        build_step = next(step for step in steps if step["name"] == step_name)
        build_config = cast(dict[str, object], build_step["with"])

        assert build_config["provenance"] == "mode=max"
        assert build_config["sbom"] is True

        used_actions = [cast(str, step.get("uses", "")) for step in steps]
        assert not any(action.startswith("actions/attest-") for action in used_actions)


def test_tracker_and_doc_only_changes_do_not_trigger_main_or_pr_gates() -> None:
    ignored_paths = ["docs/**", "**/*.md"]

    workflows = [
        (_workflow(MAIN_WORKFLOW), "push"),
        (_workflow(PR_WORKFLOW), "pull_request"),
        (_workflow(RELEASE_WORKFLOW), "push"),
        (_workflow(SEMGREP_WORKFLOW), "push"),
        (_workflow(SEMGREP_WORKFLOW), "pull_request"),
    ]

    for workflow, trigger_name in workflows:
        trigger = cast(dict[str, Any], _workflow_triggers(workflow)[trigger_name])

        assert trigger["paths-ignore"] == ignored_paths


def test_main_workflow_cancels_superseded_runs() -> None:
    workflow = _workflow(MAIN_WORKFLOW)
    concurrency = cast(dict[str, object], workflow["concurrency"])

    assert concurrency["group"] == "main-${{ github.ref }}"
    assert concurrency["cancel-in-progress"] is True


def test_main_publish_is_fast_single_arch_lane_decoupled_from_validation() -> None:
    workflow = _workflow(MAIN_WORKFLOW)
    jobs = cast(dict[str, Any], workflow["jobs"])
    publish = cast(dict[str, Any], jobs["publish"])
    build_step = next(
        step for step in _publish_steps() if step["name"] == "Build + push (multi-arch)"
    )
    build_config = cast(dict[str, object], build_step["with"])

    assert "needs" not in publish
    assert build_config["platforms"] == "linux/amd64"


def test_main_publish_uses_registry_build_cache() -> None:
    build_step = next(
        step for step in _publish_steps() if step["name"] == "Build + push (multi-arch)"
    )
    build_config = cast(dict[str, object], build_step["with"])

    cache_ref = "type=registry,ref=ghcr.io/${{ github.repository }}:buildcache"

    assert build_config["cache-from"] == cache_ref
    assert build_config["cache-to"] == f"{cache_ref},mode=max"


def test_main_and_reusable_container_builds_use_local_docker_buildx_driver() -> None:
    buildx_steps = [
        next(step for step in _publish_steps() if step["name"] == "Set up Docker Buildx"),
        next(step for step in _pr_container_steps() if step["name"] == "Set up Docker Buildx"),
    ]

    for step in buildx_steps:
        assert cast(dict[str, str], step["with"])["driver"] == "docker"


def test_reusable_pr_validation_does_not_cancel_main_runs() -> None:
    workflow = _workflow(PR_WORKFLOW)
    concurrency = cast(dict[str, str], workflow["concurrency"])

    assert concurrency["cancel-in-progress"] == "${{ github.event_name == 'pull_request' }}"


def test_reusable_pr_validation_accepts_fast_test_scope() -> None:
    workflow = _workflow(PR_WORKFLOW)
    triggers = _workflow_triggers(workflow)
    workflow_call = cast(dict[str, Any], triggers["workflow_call"])
    inputs = cast(dict[str, Any], workflow_call["inputs"])

    test_scope = cast(dict[str, Any], inputs["test-scope"])

    assert test_scope["default"] == "full"
    assert "fast" in test_scope["description"]


def test_manual_pr_validation_accepts_full_or_fast_test_scope() -> None:
    workflow = _workflow(PR_WORKFLOW)
    triggers = _workflow_triggers(workflow)
    workflow_dispatch = cast(dict[str, Any], triggers["workflow_dispatch"])
    inputs = cast(dict[str, Any], workflow_dispatch["inputs"])

    test_scope = cast(dict[str, Any], inputs["test-scope"])

    assert test_scope["default"] == "full"
    assert test_scope["type"] == "choice"
    assert test_scope["options"] == ["full", "fast"]


def test_main_validation_uses_fast_test_scope() -> None:
    workflow = _workflow(MAIN_WORKFLOW)
    validate = cast(dict[str, Any], cast(dict[str, Any], workflow["jobs"])["validate"])

    assert cast(dict[str, str], validate["with"])["test-scope"] == "fast"


def test_pip_audit_exports_runtime_dependencies_without_dev_tooling() -> None:
    audit_step = _pr_python_step("pip-audit")
    run_script = cast(str, audit_step["run"])

    assert "uv export --no-dev --no-emit-project --no-hashes" in run_script
    assert "uv run pip-audit --strict --requirement /tmp/audit-reqs.txt" in run_script


def test_fast_pr_validation_does_not_run_full_integration_coverage_sweep() -> None:
    run_script = cast(str, _pr_python_pytest_step()["run"])

    assert "inputs.test-scope" in run_script
    assert "tests/unit tests/contract" in run_script
    assert '-m "not slow"' in run_script
    assert "--cov-fail-under=90" not in run_script


def test_pr_validation_does_not_mask_failures_with_pytest_reruns() -> None:
    run_script = cast(str, _pr_python_pytest_step()["run"])
    pyproject = PYPROJECT.read_text()

    assert "--reruns" not in run_script
    assert "--reruns-delay" not in run_script
    assert "pytest-rerunfailures" not in pyproject


def test_pr_validation_fails_on_resource_warnings_and_profiles_slowest_tests() -> None:
    run_script = cast(str, _pr_python_pytest_step()["run"])

    assert "PYTHONWARNINGS='error::ResourceWarning'" in run_script
    assert "pytest -n auto --dist=loadfile tests/unit tests/contract" in run_script
    assert 'pytest -n auto --dist=loadfile -m "not slow"' in run_script
    assert run_script.count("--durations=") >= 2


def test_fast_pr_validation_skips_container_sbom_and_vulnerability_scan() -> None:
    container = _pr_container_job()

    assert container["if"] == "${{ inputs.test-scope != 'fast' }}"


def test_pr_validation_smokes_migrations_against_postgres_15_and_16() -> None:
    job = _pr_postgres_migrations_job()
    strategy = cast(dict[str, Any], job["strategy"])
    matrix = cast(dict[str, Any], strategy["matrix"])
    services = cast(dict[str, Any], job["services"])
    postgres = cast(dict[str, Any], services["postgres"])
    steps = cast(list[dict[str, Any]], job["steps"])
    migration_step = next(step for step in steps if step["name"] == "Alembic upgrade head")

    assert job["if"] == "${{ inputs.test-scope != 'fast' }}"
    assert matrix["postgres-version"] == ["15", "16"]
    assert postgres["image"] == "postgres:${{ matrix.postgres-version }}-bookworm"
    assert "TW_DATABASE_URL" in cast(str, migration_step["run"])
    assert "uv run alembic upgrade head" in cast(str, migration_step["run"])


def test_full_pr_validation_runs_playwright_against_compose_stack() -> None:
    job = _pr_playwright_job()
    steps = cast(list[dict[str, Any]], job["steps"])
    run_step = next(step for step in steps if step["name"] == "Playwright e2e")
    compose_up_step = next(step for step in steps if step["name"] == "Start compose app")
    install_step = next(step for step in steps if step["name"] == "Install Playwright browsers")

    assert job["if"] == "${{ inputs.test-scope != 'fast' }}"
    assert "python" in cast(list[str], job["needs"])
    assert "frontend" in cast(list[str], job["needs"])
    assert "docker compose -f docker/docker-compose.yml up -d --build app" in cast(
        str, compose_up_step["run"]
    )
    assert "npx playwright install --with-deps chromium" in cast(str, install_step["run"])
    assert "npm run test:e2e" in cast(str, run_step["run"])


def test_fast_pr_validation_allows_missing_coverage_artifact() -> None:
    workflow = _workflow(PR_WORKFLOW)
    upload_steps = [
        step
        for step in cast(list[dict[str, Any]], workflow["jobs"]["python"]["steps"])
        if step.get("name") == "Upload coverage XML"
    ]

    assert upload_steps
    assert upload_steps[0]["with"]["if-no-files-found"] == "ignore"


def test_frontend_audit_gate_tolerates_unavailable_npm_audit_endpoint() -> None:
    audit_step = next(
        step
        for step in _pr_frontend_steps()
        if step["name"] == "Block malicious or critical dependencies"
    )
    run_script = cast(str, audit_step["run"])

    assert 'if [ -z "$audit" ]; then' in run_script
    assert "npm audit --audit-level=critical" not in run_script

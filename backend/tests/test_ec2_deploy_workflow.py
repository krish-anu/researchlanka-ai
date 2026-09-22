"""Exercise the SSH deployment script with a CLI that reads standard input."""

import os
from pathlib import Path
import subprocess

import pytest
import yaml


WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/deploy-main-to-ec2.yml"


@pytest.mark.parametrize("migration_exit", [0, 17])
def test_migration_preserves_remaining_remote_commands(tmp_path, migration_exit):
    workflow = yaml.safe_load(WORKFLOW.read_text())
    deploy = next(
        step["run"]
        for step in workflow["jobs"]["deploy"]["steps"]
        if step["name"] == "Deploy on EC2"
    )
    remote = deploy.split("<<'REMOTE_DEPLOY'\n", 1)[1].split("\nREMOTE_DEPLOY", 1)[0]
    # Avoid the production script's fixed temporary path during this test.
    remote = remote.replace("/tmp/researchlanka-compose.ok", str(tmp_path / "compose.ok"))
    docker = tmp_path / "docker"
    docker.write_text(
        '#!/bin/bash\n'
        'printf "%s\\n" "$*" >> "$DOCKER_LOG"\n'
        'if [[ " $* " == *" run "* ]]; then\n'
        '  cat >/dev/null\n'
        '  exit "$MIGRATION_EXIT"\n'
        'fi\n'
    )
    docker.chmod(0o755)
    log = tmp_path / "docker.log"
    result = subprocess.run(
        ["bash", "-s"],
        input=remote,
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "APP_DIR": str(tmp_path),
            "DOCKER_LOG": str(log),
            "MIGRATION_EXIT": str(migration_exit),
        },
        timeout=10,
    )
    commands = log.read_text()
    restart = "up -d --force-recreate --remove-orphans api frontend"
    assert result.returncode == migration_exit, result.stderr
    if migration_exit:
        assert restart not in commands
        assert "image prune" not in commands
    else:
        assert restart in commands
        assert commands.rstrip().endswith(" ps")

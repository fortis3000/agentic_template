import os
import subprocess
import sys
from pathlib import Path

import pytest

# Paths to the scripts
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
START_ISSUE_SCRIPT = PROJECT_ROOT / ".agents" / "skills" / "gh-cli" / "scripts" / "start_issue.sh"
SUBMIT_PR_SCRIPT = PROJECT_ROOT / ".agents" / "skills" / "gh-cli" / "scripts" / "submit_pr.sh"


@pytest.fixture
def mock_git_repo(tmp_path):
    """Creates a temporary, initialized Git repository for testing scripts."""
    # Create origin bare repository
    origin_dir = tmp_path / "origin_repo"
    origin_dir.mkdir()
    subprocess.run(["git", "init", "--bare"], cwd=origin_dir, check=True)

    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()

    # Run git init
    subprocess.run(["git", "init"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True)

    # Git worktree needs at least one commit on main/master
    dummy_file = repo_dir / "README.md"
    dummy_file.write_text("# Test Repo")
    subprocess.run(["git", "add", "README.md"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=repo_dir, check=True)

    # Rename default branch to main and set up remote
    subprocess.run(["git", "branch", "-M", "main"], cwd=repo_dir, check=True)
    subprocess.run(["git", "remote", "add", "origin", str(origin_dir)], cwd=repo_dir, check=True)
    subprocess.run(["git", "push", "-u", "origin", "main"], cwd=repo_dir, check=True)

    return repo_dir


@pytest.fixture
def mock_gh_cli(tmp_path, monkeypatch):
    """Sets up a mock 'gh' executable to log CLI calls and avoid network/auth dependencies."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    mock_gh = bin_dir / "gh"
    log_file = tmp_path / "gh_calls.log"

    # Python script acting as mock gh CLI
    mock_gh_code = f"""#!{sys.executable}
import sys
import os

log_file = {repr(str(log_file))}
with open(log_file, "a") as f:
    f.write(" ".join(sys.argv[1:]) + "\\n")
sys.exit(0)
"""
    mock_gh.write_text(mock_gh_code)
    mock_gh.chmod(0o755)

    # Mock docker to simulate missing or bypass check
    mock_docker = bin_dir / "docker"
    mock_docker_code = f"""#!{sys.executable}
import sys
sys.exit(1)
"""
    mock_docker.write_text(mock_docker_code)
    mock_docker.chmod(0o755)

    # Prepend the bin directory to PATH
    path_env = os.environ.get("PATH", "")
    monkeypatch.setenv("PATH", f"{bin_dir}:{path_env}")
    monkeypatch.setenv("MOCK_GH_CALL_LOG", str(log_file))

    return log_file


def test_start_issue_creates_worktree(mock_git_repo, mock_gh_cli):
    """Tests that start_issue.sh assigns the issue and creates a git worktree."""
    issue_num = "42"
    branch_name = "test-feature-branch"

    # Run start_issue.sh
    result = subprocess.run(
        ["bash", str(START_ISSUE_SCRIPT), issue_num, branch_name],
        check=False,
        cwd=mock_git_repo,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        f"Script failed with output: {result.stderr}\nStdout: {result.stdout}"
    )

    # Verify git worktree directory exists
    worktree_dir = mock_git_repo / ".worktrees" / branch_name
    assert worktree_dir.exists()
    assert (worktree_dir / ".git").exists()

    # Check that gh commands were logged
    assert mock_gh_cli.exists()
    calls = mock_gh_cli.read_text().splitlines()
    assert any("issue edit 42 --add-assignee @me" in call for call in calls)
    assert any(f"issue develop 42 --name {branch_name}" in call for call in calls)


def test_submit_pr_from_worktree(mock_git_repo, mock_gh_cli):
    """Tests that submit_pr.sh commits, pushes, and creates a draft PR from a worktree."""
    branch_name = "test-pr-branch"

    # 1. Create a worktree first
    subprocess.run(
        ["bash", str(START_ISSUE_SCRIPT), "100", branch_name],
        cwd=mock_git_repo,
        check=True,
    )

    worktree_dir = mock_git_repo / ".worktrees" / branch_name

    # Mock docker to simulate missing or bypass check, so it runs local fallback
    # Since we want to test git staging and commit inside the worktree
    # We edit/create a file in the worktree
    new_file = worktree_dir / "new_module.py"
    new_file.write_text("print('hello')\n")

    # Run submit_pr.sh inside the worktree
    result = subprocess.run(
        ["bash", str(SUBMIT_PR_SCRIPT), "feat", "core", "add new module"],
        check=False,
        cwd=worktree_dir,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        f"Script failed with output: {result.stderr}\nStdout: {result.stdout}"
    )

    # Verify commit message
    git_log = subprocess.run(
        ["git", "log", "-1", "--pretty=%B"],
        cwd=worktree_dir,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "feat(core): add new module" in git_log.stdout

    # Verify gh command to create draft PR was called
    assert mock_gh_cli.exists()
    calls = mock_gh_cli.read_text().splitlines()
    assert any("pr create --fill --draft" in call for call in calls)

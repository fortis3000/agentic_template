import subprocess
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).parent.parent / ".agents" / "scripts" / "validate_commit_message.sh"


def run_validation_script(message: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT_PATH)],
        input=message,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    "message",
    [
        "feat: add user authentication",
        "fix(login): resolve incorrect password error",
        "docs!: update readme with breaking changes",
        "refactor(db): rename migrations table",
        "ci: configure github actions pipeline",
        "perf(engine): optimize query response time\n\nMore details in the body.",
        "feat(api)!: drop support for v1 endpoints",
    ],
)
def test_valid_commit_messages(message: str):
    result = run_validation_script(message)
    assert result.returncode == 0, (
        f"Expected valid commit message: {message}. Error: {result.stderr}"
    )


@pytest.mark.parametrize(
    "message,expected_error",
    [
        (
            "added a new feature",
            "Error: Subject line does not follow Conventional Commits format.",
        ),
        (
            "invalidtype: some description",
            "Error: Subject line does not follow Conventional Commits format.",
        ),
        (
            "feat : add space before colon",
            "Error: Subject line does not follow Conventional Commits format.",
        ),
        (
            "feat(auth) : add space before colon with scope",
            "Error: Subject line does not follow Conventional Commits format.",
        ),
        (
            "feat:",
            "Error: Subject line does not follow Conventional Commits format.",
        ),
        (
            "",
            "Error: Commit message is empty.",
        ),
        (
            "# just comments\n# in the message",
            "Error: Commit message is empty.",
        ),
        (
            "feat: " + "a" * 80,
            "Error: Subject line exceeds 72 characters",
        ),
    ],
)
def test_invalid_commit_messages(message: str, expected_error: str):
    result = run_validation_script(message)
    assert result.returncode == 1
    assert expected_error in result.stderr


@pytest.mark.parametrize(
    "message",
    [
        "Merge branch 'main' of github.com:org/repo",
        "Merge pull request #123 from branch-name",
        "Merge remote-tracking branch 'origin/main'",
        'Revert "feat: add something"',
        "squash! feat: add something",
        "fixup! fix: some bug",
        "amend! docs: fix typo",
    ],
)
def test_ignored_commit_messages(message: str):
    result = run_validation_script(message)
    assert result.returncode == 0, (
        f"Expected ignored commit to be valid: {message}. Error: {result.stderr}"
    )

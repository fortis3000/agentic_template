import json
import subprocess
import sys
from pathlib import Path

# Path to the validation script
SCRIPT_PATH = Path(__file__).parent.parent / ".agents" / "scripts" / "validate_tool_call.py"

# Expected exit code when a tool call is blocked
BLOCK_EXIT_CODE = 2


def run_validation_script(stdin_data: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        input=stdin_data,
        capture_output=True,
        text=True,
        check=False,
    )


def test_allow_safe_commands():
    payload = {
        "tool_name": "run_command",
        "tool_input": {"CommandLine": "ls -la"},
    }
    result = run_validation_script(json.dumps(payload))
    assert result.returncode == 0
    assert result.stderr == ""


def test_allow_other_tools():
    payload = {
        "tool_name": "view_file",
        "tool_input": {"AbsolutePath": "/some/safe/file.txt"},
    }
    result = run_validation_script(json.dumps(payload))
    assert result.returncode == 0
    assert result.stderr == ""


def test_fail_invalid_json():
    result = run_validation_script("invalid json")
    assert result.returncode == BLOCK_EXIT_CODE
    assert "Error parsing stdin" in result.stderr


def test_block_destructive_rm_rf_root():
    bad_commands = [
        "rm -rf /",
        "rm -rf /*",
        "rm -fr /",
        "rm -r -f /",
        "rm -f -r /",
        "rm -rf '/'",
        'rm -rf "/"',
        "rm -rf  /",  # multiple spaces
        " rm -rf / ",  # leading/trailing spaces
    ]

    for cmd in bad_commands:
        payload = {
            "tool_name": "run_command",
            "tool_input": {"CommandLine": cmd},
        }
        result = run_validation_script(json.dumps(payload))
        assert result.returncode == BLOCK_EXIT_CODE, f"Failed to block: {cmd}"
        assert "Destructive command detected" in result.stderr, f"Missing block message for: {cmd}"


def test_allow_non_destructive_rm():
    safe_commands = [
        "rm file.txt",
        "rm -f file.txt",
        "rm -rf file.txt",
        "rm -rf ./file.txt",
        "rm -rf /tmp/somefile",
        "echo 'rm -rf /'",
        "ls /",
    ]

    for cmd in safe_commands:
        payload = {
            "tool_name": "run_command",
            "tool_input": {"CommandLine": cmd},
        }
        result = run_validation_script(json.dumps(payload))
        assert result.returncode == 0, f"Incorrectly blocked: {cmd}"
        assert result.stderr == ""

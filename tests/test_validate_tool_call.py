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
    data = json.loads(result.stdout)
    assert data["decision"] == "allow"


def test_allow_safe_protojson_toolcall():
    payload = {
        "toolCall": {
            "name": "run_command",
            "args": {"CommandLine": "ls -la"},
        }
    }
    result = run_validation_script(json.dumps(payload))
    assert result.returncode == 0
    assert result.stderr == ""
    data = json.loads(result.stdout)
    assert data["decision"] == "allow"


def test_allow_other_safe_tools():
    payload = {
        "tool_name": "view_file",
        "tool_input": {"AbsolutePath": "/some/safe/file.txt"},
    }
    result = run_validation_script(json.dumps(payload))
    assert result.returncode == 0
    assert result.stderr == ""
    data = json.loads(result.stdout)
    assert data["decision"] == "allow"


def test_fail_invalid_json():
    result = run_validation_script("invalid json")
    assert result.returncode == BLOCK_EXIT_CODE
    assert "Error parsing stdin" in result.stderr
    data = json.loads(result.stdout)
    assert data["decision"] == "deny"


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
        data = json.loads(result.stdout)
        assert data["decision"] == "deny"


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


def test_block_env_reading_shell_commands():
    bad_commands = [
        "cat .env",
        "cat ./.env",
        "cat ../.env",
        "cat /Users/user/project/.env",
        "cat .env.local",
        "cat .env.prod",
        "cat .env.production",
        "cat .env.test",
        "cat .env.staging",
        "cat .env.vault",
        "head .env",
        "head -n 20 .env",
        "tail .env",
        "tail -f .env",
        "less .env",
        "more .env",
        "nl .env",
        "bat .env",
        "tac .env",
        "grep GITHUB_TOKEN .env",
        "grep -i secret ./.env",
        "awk '{print}' .env",
        "sed -n '1p' .env",
        "cut -d= -f2 .env",
        "strings .env",
        "xxd .env",
        "hexdump .env",
        "base64 .env",
        "source .env",
        ". .env",
        "echo hello && cat .env",
        "ls; cat .env.local",
    ]

    for cmd in bad_commands:
        payload = {
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": cmd},
            }
        }
        result = run_validation_script(json.dumps(payload))
        assert result.returncode == BLOCK_EXIT_CODE, f"Failed to block shell command: {cmd}"
        assert (
            "Reading or accessing .env file is forbidden" in result.stderr
            or "forbidden" in result.stderr
        ), f"Missing stderr reason for: {cmd}"
        data = json.loads(result.stdout)
        assert data["decision"] == "deny"


def test_block_env_redirections_and_subshells():
    bad_commands = [
        "cat < .env",
        "cat <.env",
        "head < .env.local",
        "while read line; do echo $line; done < .env",
        "echo $(cat .env)",
        "VAR=$(cat .env)",
        "echo `cat .env`",
        "$(< .env)",
        "$(<.env)",
    ]

    for cmd in bad_commands:
        payload = {
            "tool_name": "run_command",
            "tool_input": {"CommandLine": cmd},
        }
        result = run_validation_script(json.dumps(payload))
        assert result.returncode == BLOCK_EXIT_CODE, f"Failed to block redirection/subshell: {cmd}"
        data = json.loads(result.stdout)
        assert data["decision"] == "deny"


def test_block_python_reading_env():
    bad_python_commands = [
        "python -c \"open('.env').read()\"",
        "python3 -c \"open('.env').read()\"",
        "python -c 'with open(\".env\") as f: print(f.read())'",
        "python3 -c \"from pathlib import Path; print(Path('.env').read_text())\"",
        "python3 -c \"from pathlib import Path; print(Path('.env.production').read_text())\"",
        "uv run python -c \"print(open('.env').read())\"",
        "python script.py .env",
        'python3 -c "import dotenv; dotenv.load_dotenv()"',
        'python3 -c "from dotenv import dotenv_values; print(dotenv_values())"',
    ]

    for cmd in bad_python_commands:
        payload = {
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": cmd},
            }
        }
        result = run_validation_script(json.dumps(payload))
        assert result.returncode == BLOCK_EXIT_CODE, f"Failed to block Python command: {cmd}"
        data = json.loads(result.stdout)
        assert data["decision"] == "deny"


def test_block_other_interpreters_reading_env():
    bad_interpreter_commands = [
        "node -e \"console.log(fs.readFileSync('.env'))\"",
        "ruby -e \"puts File.read('.env')\"",
        "perl -pe 'print' .env",
        'bash -c "cat .env"',
        'sh -c "cat .env.local"',
    ]

    for cmd in bad_interpreter_commands:
        payload = {
            "tool_name": "run_command",
            "tool_input": {"CommandLine": cmd},
        }
        result = run_validation_script(json.dumps(payload))
        assert result.returncode == BLOCK_EXIT_CODE, f"Failed to block interpreter command: {cmd}"
        data = json.loads(result.stdout)
        assert data["decision"] == "deny"


def test_block_tools_targeting_env():
    blocked_tool_calls = [
        {"tool_name": "view_file", "tool_input": {"AbsolutePath": "/workspace/.env"}},
        {"tool_name": "view_file", "tool_input": {"AbsolutePath": ".env"}},
        {"tool_name": "view_file", "tool_input": {"AbsolutePath": ".env.local"}},
        {"tool_name": "view_file", "tool_input": {"AbsolutePath": "/workspace/.env.production"}},
        {"tool_name": "grep_search", "tool_input": {"SearchPath": ".env"}},
        {"tool_name": "grep_search", "tool_input": {"SearchPath": "/workspace/.env"}},
        {"tool_name": "read_resource", "tool_input": {"Uri": "file:///workspace/.env"}},
        {"tool_name": "read_url_content", "tool_input": {"Url": "file:///workspace/.env"}},
        {
            "toolCall": {
                "name": "view_file",
                "args": {"AbsolutePath": "/workspace/.env"},
            }
        },
    ]

    for payload in blocked_tool_calls:
        result = run_validation_script(json.dumps(payload))
        assert result.returncode == BLOCK_EXIT_CODE, f"Failed to block tool call: {payload}"
        assert "Access to .env file is forbidden" in result.stderr
        data = json.loads(result.stdout)
        assert data["decision"] == "deny"


def test_allow_safe_env_templates():
    safe_template_commands = [
        "cat .env.example",
        "cat ./.env.example",
        "cat /path/to/.env.example",
        "cat .env.template",
        "cat .env.sample",
        "cat .env.dist",
        "cat .env.schema",
        "python -c \"open('.env.example').read()\"",
        "python3 -c \"import dotenv; dotenv.load_dotenv('.env.example')\"",
    ]

    for cmd in safe_template_commands:
        payload = {
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": cmd},
            }
        }
        result = run_validation_script(json.dumps(payload))
        assert result.returncode == 0, f"Incorrectly blocked safe template: {cmd}"
        assert result.stderr == ""
        data = json.loads(result.stdout)
        assert data["decision"] == "allow"

    safe_tool_calls = [
        {"tool_name": "view_file", "tool_input": {"AbsolutePath": "/workspace/.env.example"}},
        {"tool_name": "view_file", "tool_input": {"AbsolutePath": ".env.template"}},
        {"tool_name": "view_file", "tool_input": {"AbsolutePath": ".env.sample"}},
    ]

    for payload in safe_tool_calls:
        result = run_validation_script(json.dumps(payload))
        assert result.returncode == 0, f"Incorrectly blocked safe tool call: {payload}"
        assert result.stderr == ""
        data = json.loads(result.stdout)
        assert data["decision"] == "allow"


def test_allow_safe_commands_referencing_env_names():
    safe_commands = [
        "python -c \"print('hello world')\"",
        "python -c \"import os; print(os.environ.get('HOME'))\"",
        "python -c \"import os; print(os.getenv('ENVIRONMENT'))\"",
        "python -m pytest",
        "uv run ruff check",
        'git commit -m "feat(config): support custom env variables"',
        'echo "ENVIRONMENT=production"',
        "cat pyproject.toml",
    ]

    for cmd in safe_commands:
        payload = {
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": cmd},
            }
        }
        result = run_validation_script(json.dumps(payload))
        assert result.returncode == 0, f"Incorrectly blocked safe command: {cmd}"
        assert result.stderr == ""
        data = json.loads(result.stdout)
        assert data["decision"] == "allow"

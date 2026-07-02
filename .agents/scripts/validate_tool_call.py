import json
import re
import shlex
import sys


def check_destructive_command(command_line: str) -> bool:
    """Check if the command line has a destructive rm -rf / or similar pattern."""
    # Normalize command line (remove extra whitespaces)
    normalized_cmd = re.sub(r"\s+", " ", command_line.strip())

    try:
        parts = shlex.split(normalized_cmd)
    except Exception:
        parts = normalized_cmd.split(" ")

    # Find all indices of 'rm' or path ending in 'rm'
    rm_indices = [i for i, x in enumerate(parts) if x == "rm" or x.endswith("/rm")]

    for rm_idx in rm_indices:
        # Check if there is a recursive flag anywhere after 'rm'
        has_recursive = False
        for part in parts[rm_idx + 1 :]:
            if part.startswith("-") and not part.startswith("--"):
                # Short flags: check for 'r' or 'R' (e.g., -rf, -fr, -r)
                if any(c in part for c in ("r", "R")):
                    has_recursive = True
            elif part in ("--recursive", "-r", "-R"):
                has_recursive = True

        if has_recursive:
            # Check if any path argument after 'rm' targets the root directory
            for part in parts[rm_idx + 1 :]:
                if not part.startswith("-"):
                    clean_part = part.strip("'\"")
                    if clean_part in ("/", "/*") or clean_part.startswith("/*"):
                        return True

    return False


def main():
    try:
        input_data = json.load(sys.stdin)
    except Exception as e:
        sys.stderr.write(f"Error parsing stdin: {e}\n")
        # Fail closed for security if JSON parsing fails on expected input
        sys.exit(2)

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    # Only shell-command tools carry a command line worth validating.
    # Anything else has nothing to check, so allow it through instead of
    # crashing on an undefined command_line.
    if tool_name not in ("run_command", "Bash", "bash", "execute_command"):
        sys.exit(0)

    command_line = tool_input.get("CommandLine", tool_input.get("command", ""))
    if not isinstance(command_line, str):
        command_line = str(command_line)

    if check_destructive_command(command_line):
        sys.stderr.write(f"Block tool execution: Destructive command detected: {command_line}\n")
        sys.exit(2)  # Block code

    sys.exit(0)


if __name__ == "__main__":
    main()

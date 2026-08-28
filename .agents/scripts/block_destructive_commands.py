from __future__ import annotations

import json
import re
import shlex
import sys

BLOCK_EXIT_CODE = 2


def check_destructive_command(command_line: str) -> bool:
    """Check if the command line has a destructive rm pattern targeting root."""
    normalized_cmd = re.sub(r"\s+", " ", command_line.strip())

    try:
        parts = shlex.split(normalized_cmd)
    except Exception:
        parts = normalized_cmd.split(" ")

    rm_indices = [i for i, x in enumerate(parts) if x == "rm" or x.endswith("/rm")]

    for rm_idx in rm_indices:
        has_recursive = False
        for part in parts[rm_idx + 1 :]:
            if part.startswith("-") and not part.startswith("--"):
                if any(c in part for c in ("r", "R")):
                    has_recursive = True
            elif part in ("--recursive", "-r", "-R"):
                has_recursive = True

        if has_recursive:
            for part in parts[rm_idx + 1 :]:
                if not part.startswith("-"):
                    clean_part = part.strip("'\"")
                    if clean_part in ("/", "/*") or clean_part.startswith("/*"):
                        return True

    return False


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except Exception as e:
        sys.stderr.write(f"Error parsing stdin: {e}\n")
        print(json.dumps({"decision": "deny", "reason": f"Invalid JSON stdin: {e}"}))
        sys.exit(BLOCK_EXIT_CODE)

    tool_call = input_data.get("toolCall", {})
    tool_name = tool_call.get("name", input_data.get("tool_name", ""))
    tool_input = tool_call.get("args", input_data.get("tool_input", {}))

    if tool_name in ("run_command", "Bash", "bash", "execute_command"):
        command_line = tool_input.get("CommandLine", tool_input.get("command", ""))
        if not isinstance(command_line, str):
            command_line = str(command_line)

        if check_destructive_command(command_line):
            reason = f"Destructive command detected: {command_line}"
            sys.stderr.write(f"Block tool execution: {reason}\n")
            print(json.dumps({"decision": "deny", "reason": "Destructive command detected"}))
            sys.exit(BLOCK_EXIT_CODE)

    print(json.dumps({"decision": "allow"}))
    sys.exit(0)


if __name__ == "__main__":
    main()

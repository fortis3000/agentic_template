#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
from __future__ import annotations

import json
import re
import shlex
import sys
from typing import Any

BLOCK_EXIT_CODE = 2
MIN_ENV_FILENAME_LEN = 4

ENV_SAFE_SUFFIXES = {
    "example",
    "sample",
    "template",
    "dist",
    "schema",
    "default",
    "example.local",
    "sample.local",
    "template.local",
}


def extract_env_references(text: str) -> list[str]:
    """Extract all .env file references from a text string, excluding safe templates like .env.example."""
    if not text or not isinstance(text, str):
        return []

    found = []
    # Match exact .env (not followed by word chars or dot, e.g. not .environ, not .env.local)
    for _ in re.finditer(r"(?<![a-zA-Z0-9_])\.env(?![a-zA-Z0-9_.])", text):
        found.append(".env")

    # Match .env.<suffix>
    for m in re.finditer(r"(?<![a-zA-Z0-9_])\.env\.([a-zA-Z0-9_.-]+)\b", text):
        suffix_parts = m.group(1).lower().split(".")
        suffix = suffix_parts[0]
        full_suffix = m.group(1).lower()
        if suffix not in ENV_SAFE_SUFFIXES and full_suffix not in ENV_SAFE_SUFFIXES:
            found.append(f".env.{m.group(1)}")

    return found


def is_env_filename(name: str) -> bool:
    """Check if a filename matches .env or .env.<variant> (excluding safe templates like .env.example)."""
    if not name or not isinstance(name, str):
        return False
    clean_name = name.strip("'\"`")
    if clean_name == ".env":
        return True
    if clean_name.startswith(".env."):
        suffix = clean_name[5:].lower()
        if suffix in ENV_SAFE_SUFFIXES:
            return False
        return True
    if (
        clean_name.endswith(".env")
        and not clean_name.startswith(".")
        and len(clean_name) > MIN_ENV_FILENAME_LEN
    ):
        return True
    return False


def is_env_path(path_str: str) -> bool:
    """Check if a path string points to a .env file."""
    if not path_str or not isinstance(path_str, str):
        return False
    clean_path = path_str.strip().strip("'\"`")
    if clean_path.startswith("file://"):
        clean_path = clean_path[7:]

    clean_path = clean_path.replace("\\", "/")
    parts = [p for p in clean_path.rstrip("/").split("/") if p]
    if not parts:
        return False

    filename = parts[-1]
    return is_env_filename(filename)


def check_destructive_command(command_line: str) -> bool:
    """Check if the command line has a destructive rm -rf / or similar pattern."""
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


def check_env_in_tool_args(tool_input: dict[str, Any]) -> bool:
    """Check if structured tool input parameters target a .env file."""
    if not isinstance(tool_input, dict):
        return False

    path_keys = (
        "AbsolutePath",
        "SearchPath",
        "FilePath",
        "TargetFile",
        "SearchDirectory",
        "path",
        "file_path",
        "target_file",
        "directory",
        "Uri",
        "uri",
        "Url",
        "url",
        "filename",
        "file",
    )

    for k in path_keys:
        val = tool_input.get(k)
        if isinstance(val, str) and (is_env_path(val) or extract_env_references(val)):
            return True
        if isinstance(val, list) and any(
            isinstance(item, str) and (is_env_path(item) or extract_env_references(item))
            for item in val
        ):
            return True

    for k in ("Includes", "Pattern", "Excludes"):
        val = tool_input.get(k)
        if isinstance(val, str) and is_env_filename(val):
            return True
        if isinstance(val, list) and any(
            isinstance(item, str) and is_env_filename(item) for item in val
        ):
            return True

    return False


def strip_wrappers(tokens: list[str]) -> list[str]:
    """Strip execution wrapper commands like sudo, uv run, env."""
    idx = 0
    while idx < len(tokens):
        t = tokens[idx]
        if t in ("sudo", "env", "nohup", "time", "xargs"):
            idx += 1
        elif t == "uv" and idx + 1 < len(tokens) and tokens[idx + 1] == "run":
            idx += 2
        else:
            break
    return tokens[idx:] if idx < len(tokens) else tokens


def has_env_reference(tokens: list[str]) -> bool:
    """Check if any token references a non-safe .env file."""
    return any(extract_env_references(token) or is_env_path(token) for token in tokens)


def is_exempt_command(base_cmd: str, args: list[str]) -> bool:
    """Check if the command is exempt from .env blocking (e.g. echo or git commit)."""
    if base_cmd in ("echo", "printf", "touch"):
        return not any(
            a in ("<", "0<") and i + 1 < len(args) and is_env_path(args[i + 1])
            for i, a in enumerate(args)
        )
    if base_cmd == "git":
        git_subcmd = args[0] if args else ""
        return git_subcmd in ("commit", "status", "check-ignore", "add", "rm", "branch")
    return False


def check_single_command_tokens(tokens: list[str]) -> bool:
    """Check if a single command (tokenized) reads or accesses .env."""
    effective_tokens = strip_wrappers(tokens)
    if not effective_tokens or not has_env_reference(effective_tokens):
        return False

    base_cmd = effective_tokens[0].split("/")[-1]
    return not is_exempt_command(base_cmd, effective_tokens[1:])


def check_redirections(norm_cmd: str) -> bool:
    """Check for input redirections from .env files."""
    unquoted = re.findall(r"(?:<|0<)\s*([^\s;&|<>()\'\"]+)", norm_cmd)
    quoted = re.findall(r"""(?:<|0<)\s*['"]([^'"]+)['"]""", norm_cmd)
    return any(
        is_env_path(target) or extract_env_references(target) for target in (unquoted + quoted)
    )


def check_subshells(norm_cmd: str) -> bool:
    """Check for subshells or backtick commands accessing .env."""
    subcmds = re.findall(r"\$\(([^)]+)\)", norm_cmd) + re.findall(r"`([^`]+)`", norm_cmd)
    return any(check_env_read_in_command(subcmd) for subcmd in subcmds)


def check_env_read_in_command(command_line: str) -> bool:
    """Check if a shell command attempts to read or access a .env file."""
    if not command_line or not isinstance(command_line, str):
        return False

    norm_cmd = command_line.strip()
    if check_redirections(norm_cmd):
        return True

    if re.search(r"(?:dotenv\.load_dotenv|load_dotenv|dotenv_values)\s*\(", norm_cmd) and not any(
        suffix in norm_cmd for suffix in ("example", "template", "sample")
    ):
        return True

    if check_subshells(norm_cmd):
        return True

    try:
        lexer = shlex.shlex(norm_cmd, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        all_tokens = list(lexer)
    except Exception:
        try:
            all_tokens = shlex.split(norm_cmd)
        except Exception:
            all_tokens = norm_cmd.split()

    current_cmd_tokens: list[str] = []
    for token in all_tokens:
        if token in (";", "&&", "||", "|", "&", "\n"):
            if check_single_command_tokens(current_cmd_tokens):
                return True
            current_cmd_tokens = []
        else:
            current_cmd_tokens.append(token)

    return check_single_command_tokens(current_cmd_tokens)


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

    # Check structured tool arguments for .env file paths (e.g. view_file, grep_search)
    if check_env_in_tool_args(tool_input):
        reason = "Access to .env file is forbidden to protect sensitive credentials."
        sys.stderr.write(f"Block tool execution: {reason}\n")
        print(json.dumps({"decision": "deny", "reason": reason}))
        sys.exit(BLOCK_EXIT_CODE)

    # Check command line tools
    if tool_name in ("run_command", "Bash", "bash", "execute_command"):
        command_line = tool_input.get("CommandLine", tool_input.get("command", ""))
        if not isinstance(command_line, str):
            command_line = str(command_line)

        if check_destructive_command(command_line):
            sys.stderr.write(
                f"Block tool execution: Destructive command detected: {command_line}\n"
            )
            print(json.dumps({"decision": "deny", "reason": "Destructive command detected"}))
            sys.exit(BLOCK_EXIT_CODE)

        if check_env_read_in_command(command_line):
            reason = "Reading or accessing .env file is forbidden to protect sensitive credentials."
            sys.stderr.write(f"Block tool execution: {reason} Command: {command_line}\n")
            print(json.dumps({"decision": "deny", "reason": reason}))
            sys.exit(BLOCK_EXIT_CODE)

    print(json.dumps({"decision": "allow"}))
    sys.exit(0)


if __name__ == "__main__":
    main()

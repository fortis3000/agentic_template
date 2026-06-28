import json
import os
import re
import sys
from collections.abc import Iterable
from typing import Dict, List, Tuple

# Fallback values if the template file cannot be loaded
FALLBACK_REQUIRED_SECTIONS = {
    "summary": "Summary",
    "key changes": "Key Changes",
    "discussion & pitfalls": "Discussion & Pitfalls",
    "verification": "Verification",
}

DEFAULT_TEMPLATE_PATH = ".github/pull_request_template.md"
MIN_LENGTH = 10


def extract_template_sections(template_path: str) -> Dict[str, str]:
    """Reads the template file and parses it to find all required sections.

    Returns a mapping of normalized section header -> canonical/original section name.
    e.g., {"summary": "Summary", "key changes": "Key Changes", ...}
    """
    if not os.path.exists(template_path):
        return FALLBACK_REQUIRED_SECTIONS

    try:
        with open(template_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"Warning: Failed to read template {template_path}: {e}", file=sys.stderr)
        return FALLBACK_REQUIRED_SECTIONS

    # Find any line starting with '#' followed by spaces and the section name
    header_regex = re.compile(r"^#+(?:\s+(.*))?$", re.MULTILINE)
    sections: Dict[str, str] = {}
    for match in header_regex.finditer(content):
        header_text = (match.group(1) or "").strip()
        if header_text:
            normalized = header_text.lower()
            # Ignore the main top-level PR header (like "Pull Request")
            if normalized not in ("pull request", "pr"):
                sections[normalized] = header_text

    # If we failed to find any sections, return the fallback
    if not sections:
        return FALLBACK_REQUIRED_SECTIONS

    return sections


def parse_sections(body: str, required_keys: Iterable[str]) -> Dict[str, str]:
    """Parses the PR body into sections based on markdown headers.

    Args:
        body (str): The markdown body of the PR.
        required_keys (Iterable[str]): Normalized required keys to search for.

    Returns:
        Dict[str, str]: A mapping of normalized section keys to section content.
    """
    # Regex to find any header: a line starting with one or more '#'
    header_regex = re.compile(r"^#+(?:\s+(.*))?$", re.MULTILINE)

    # Find all headers and their positions
    headers: List[Tuple[str, int, int]] = []  # (header_text, start_pos, end_pos)
    for match in header_regex.finditer(body):
        header_text = (match.group(1) or "").strip().lower()
        headers.append((header_text, match.start(), match.end()))

    sections: Dict[str, str] = {}

    for i, (header_text, start, end) in enumerate(headers):
        if header_text in required_keys:
            # Content goes until the next header (of any kind) or end of body
            next_start = headers[i + 1][1] if i + 1 < len(headers) else len(body)
            content = body[end:next_start]
            sections[header_text] = content

    return sections


def validate_pr_body(body: str, template_path: str = DEFAULT_TEMPLATE_PATH) -> List[str]:
    """Validates that all required sections are present and correctly filled out.

    Args:
        body (str): The markdown body of the PR.
        template_path (str): Path to the PR template markdown file.

    Returns:
        List[str]: A list of error messages. Empty if validation passes.
    """
    errors: List[str] = []

    if not body or not body.strip():
        return ["PR description is empty. Please fill out the PR template."]

    required_sections = extract_template_sections(template_path)
    sections = parse_sections(body, required_sections.keys())

    placeholder = "[answer here]"

    for key, display_name in required_sections.items():
        if key not in sections:
            errors.append(f"Missing required section: '## {display_name}'")
            continue

        content = sections[key]

        # Clean content: strip HTML comments
        content_cleaned = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
        content_cleaned = content_cleaned.strip()

        # Check for placeholder text (standalone [Answer here] or with list bullets)
        placeholder_regex = re.compile(
            r"^\s*(?:[-*+]\s*)?" + re.escape(placeholder) + r"\s*$", re.IGNORECASE | re.MULTILINE
        )
        if placeholder_regex.search(content_cleaned):
            errors.append(f"Section '## {display_name}' contains the default placeholder text.")

        # Remove placeholder text and questions for length verification
        content_for_len = placeholder_regex.sub("", content_cleaned)

        # Strip the questions themselves (lines ending with '?*' inside '*' formatting)
        content_for_len = re.sub(r"^\s*\*.*?\?\*\s*$", "", content_for_len, flags=re.MULTILINE)

        # Strip empty list bullets or syntax markers left behind
        content_for_len = re.sub(r"^\s*[-*+]\s*$", "", content_for_len, flags=re.MULTILINE)
        content_for_len = content_for_len.strip()

        if len(content_for_len) < MIN_LENGTH:
            errors.append(
                f"Section '## {display_name}' content is too short "
                f"(minimum {MIN_LENGTH} characters required, got {len(content_for_len)})."
            )

    return errors


def main() -> None:
    """Main CLI entrypoint to validate a PR body."""
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    body = None

    if event_path and os.path.exists(event_path):
        try:
            with open(event_path, "r", encoding="utf-8") as f:
                event_data = json.load(f)
                body = event_data.get("pull_request", {}).get("body")
        except Exception as e:
            print(f"Warning: Failed to parse GITHUB_EVENT_PATH: {e}", file=sys.stderr)

    if body is None:
        if len(sys.argv) > 1:
            file_path = sys.argv[1]
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        body = f.read()
                except Exception as e:
                    print(f"Error: Failed to read file {file_path}: {e}", file=sys.stderr)
                    sys.exit(1)
            else:
                body = sys.argv[1]
        elif not sys.stdin.isatty():
            body = sys.stdin.read()

    if body is None:
        print(
            "Error: No PR body provided. Provide via GITHUB_EVENT_PATH, command argument, or stdin.",
            file=sys.stderr,
        )
        sys.exit(1)

    template_path = os.environ.get("PR_TEMPLATE_PATH", DEFAULT_TEMPLATE_PATH)
    errors = validate_pr_body(body, template_path=template_path)
    if errors:
        print("PR Validation Failed:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

    print("PR Validation Succeeded!")
    sys.exit(0)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
import sys
import re
import math
import subprocess

# Common regex patterns for secrets
PATTERNS = {
    "AWS Access Key ID": re.compile(r"AKIA[0-9A-Z]{16}"),
    "Private Key": re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----"),
    "Generic Password/Token Assignment": re.compile(
        r"(?:password|passwd|secret|token|api_key|apikey|credentials)\s*=\s*['\"]([a-zA-Z0-9_\-\.\=\+]{8,})['\"]",
        re.IGNORECASE
    )
}

def calculate_entropy(s: str) -> float:
    """Calculate the Shannon entropy of a string."""
    if not s:
        return 0.0
    probabilities = [float(s.count(c)) / len(s) for c in set(s)]
    return -sum(p * math.log2(p) for p in probabilities)

def scan_diff() -> int:
    """Scan git diff for secrets."""
    try:
        diff_output = subprocess.check_output(
            ["git", "diff", "origin/master...HEAD"],
            stderr=subprocess.DEVNULL
        ).decode("utf-8", errors="replace")
    except subprocess.CalledProcessError:
        # Fallback to local diff or working tree changes if origin/master doesn't exist
        try:
            diff_output = subprocess.check_output(
                ["git", "diff", "HEAD"],
                stderr=subprocess.DEVNULL
            ).decode("utf-8", errors="replace")
        except Exception:
            diff_output = ""

    lines = diff_output.splitlines()
    violations = 0

    for line_num, line in enumerate(lines, 1):
        if not line.startswith("+") or line.startswith("+++"):
            continue
        
        # Strip the '+' prefix
        content = line[1:].strip()
        
        # Check patterns
        for name, pattern in PATTERNS.items():
            matches = pattern.findall(content)
            for match in matches:
                # For group matches (like generic password assignment), check entropy
                val = match[0] if isinstance(match, tuple) else match
                if len(val) >= 12 and calculate_entropy(val) > 3.0:
                    print(f"VIOLATION: Line {line_num} contains a potential {name} (high entropy: {calculate_entropy(val):.2f})")
                    print(f"  Content: {content[:80]}")
                    violations += 1
                elif "Private Key" in name or "AWS" in name:
                    print(f"VIOLATION: Line {line_num} contains a potential {name}")
                    print(f"  Content: {content[:80]}")
                    violations += 1

    return violations

if __name__ == "__main__":
    sys.exit(scan_diff())

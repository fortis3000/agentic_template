import sys
from pathlib import Path

# Dynamically add the secrets scanner script directory to sys.path
script_dir = Path(__file__).parent.parent / ".agents" / "skills" / "security-guard" / "scripts"
sys.path.append(str(script_dir))

import scan_secrets  # type: ignore


def test_calculate_entropy():
    # Empty string should have 0 entropy
    assert scan_secrets.calculate_entropy("") == 0.0
    # High entropy strings should have high values
    assert scan_secrets.calculate_entropy("abcdefghijklmnopqrstuvwxyz") > 4.0
    # Repeated single character should have 0 entropy
    assert scan_secrets.calculate_entropy("aaaaaaa") == 0.0


def test_aws_key_pattern():
    pattern = scan_secrets.PATTERNS["AWS Access Key ID"]
    assert pattern.search("AKIA1234567890ABCDEF") is not None
    assert pattern.search("AKIA123") is None
    assert pattern.search("normal_string") is None


def test_private_key_pattern():
    pattern = scan_secrets.PATTERNS["Private Key"]
    assert pattern.search("-----BEGIN RSA PRIVATE KEY-----") is not None
    assert pattern.search("-----BEGIN PRIVATE KEY-----") is not None
    assert pattern.search("normal_string") is None


def test_generic_password_pattern():
    pattern = scan_secrets.PATTERNS["Generic Password/Token Assignment"]
    # Check valid assignments
    m1 = pattern.search("my_api_key = 'super_secret_value'")
    assert m1 is not None
    assert m1.group(1) == "super_secret_value"

    m2 = pattern.search("password='password123'")
    assert m2 is not None
    assert m2.group(1) == "password123"

    m3 = pattern.search("token = \"some-token-value\"")
    assert m3 is not None
    assert m3.group(1) == "some-token-value"

    # Negative cases
    assert pattern.search("normal_variable = 'value'") is None

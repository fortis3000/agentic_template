import os

import pytest

from utils.pr_validator import extract_template_sections, validate_pr_body

TEMPLATE_PATH = ".github/pull_request_template.md"


@pytest.fixture
def raw_template_body() -> str:
    """Fixture that reads the actual PR template file."""
    assert os.path.exists(TEMPLATE_PATH), f"PR template not found at {TEMPLATE_PATH}"
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def template_sections() -> dict[str, str]:
    """Fixture that extracts sections directly from the actual template."""
    return extract_template_sections(TEMPLATE_PATH)


def test_raw_template_fails_validation(raw_template_body, template_sections):
    """Verifies that the default template file fails validation due to placeholders."""
    errors = validate_pr_body(raw_template_body)
    assert errors, "Default template should not pass validation without answers."

    # Verify that errors are generated for the sections in the template
    for display_name in template_sections.values():
        assert any(display_name in err for err in errors), (
            f"Expected error for section: {display_name}"
        )


def test_filled_template_passes_validation(raw_template_body):
    """Verifies that a fully answered template passes validation."""
    # Replace all placeholders with valid answers
    filled_body = raw_template_body.replace(
        "[Answer here]", "This is a valid and sufficiently detailed answer for this section."
    )
    errors = validate_pr_body(filled_body)
    assert not errors, f"Expected filled template to pass, but got errors: {errors}"


def test_missing_sections(raw_template_body, template_sections):
    """Verifies that omitting any section defined in the template fails validation."""
    # Fill the template first
    filled_body = raw_template_body.replace(
        "[Answer here]", "This is a valid and sufficiently detailed answer for this section."
    )

    # For each section, try removing its header and assert it fails
    for display_name in template_sections.values():
        # Remove the heading (e.g. "## Summary")
        corrupted_body = filled_body.replace(f"## {display_name}", f"## Ignored {display_name}")
        errors = validate_pr_body(corrupted_body)
        assert any(f"Missing required section: '## {display_name}'" in err for err in errors), (
            f"Expected missing section error for: {display_name}"
        )


def test_answers_too_short(raw_template_body, template_sections):
    """Verifies that answers shorter than the minimum length threshold fail validation."""
    short_body = raw_template_body.replace("[Answer here]", "S")

    errors = validate_pr_body(short_body)
    assert errors, "Short answers should fail validation."

    # There should be a short content error for each section
    for display_name in template_sections.values():
        assert any(f"Section '## {display_name}' content is too short" in err for err in errors), (
            f"Expected too short error for: {display_name}"
        )


def test_placeholder_text_mentioned_in_prose(raw_template_body):
    """Verifies that referencing '[Answer here]' in normal text does not trigger failure."""
    # Fill body, but include '[Answer here]' inside a larger sentence
    filled_body = raw_template_body.replace(
        "[Answer here]",
        "We discuss that the template uses the [Answer here] placeholder in this section description.",
    )
    errors = validate_pr_body(filled_body)
    assert not errors, f"Expected no errors when placeholder is used in prose, but got: {errors}"


def test_empty_pr_body():
    """Verifies that a completely empty body fails validation."""
    errors = validate_pr_body("")
    assert len(errors) == 1
    assert "PR description is empty" in errors[0]


def test_comments_are_ignored(raw_template_body):
    """Verifies that HTML comments are stripped and ignored by the validator."""
    # Add comments around the answers, and verify they are not counted towards length
    commented_body = raw_template_body.replace(
        "[Answer here]",
        "<!-- This is a comment that should be stripped -->\n"
        "This is the actual non-comment answer text.",
    )
    errors = validate_pr_body(commented_body)
    assert not errors, f"Expected commented body to pass, but got: {errors}"

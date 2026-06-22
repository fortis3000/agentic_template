import re
from pathlib import Path
from string import Template
from typing import Any


class PromptManager:
    """Manages loading, parsing, and rendering of prompt templates."""

    def __init__(self, base_dir: str | Path | None = None, default_format: str = "f-string"):
        """Initialize the PromptManager.

        Args:
            base_dir: Optional base directory to resolve prompt template files from.
            default_format: Default formatting style ("f-string" for {var} or "template" for $var).
        """
        self.base_dir = Path(base_dir) if base_dir else None
        self.default_format = default_format

    def load_prompt(
        self,
        template_source: str,
        variables: dict[str, Any] | None = None,
        format_style: str | None = None,
    ) -> str:
        """Load and format a prompt from a string, a file path, or a file under base_dir.

        Args:
            template_source: Can be a direct template string, a relative path from base_dir, or an absolute path.
            variables: Variables to render the template with.
            format_style: Optional override for the formatting style ("f-string" or "template").

        Returns:
            The formatted prompt string.
        """
        variables = variables or {}
        style = format_style or self.default_format

        # 1. Resolve template content
        content = self._resolve_template_content(template_source)

        # 2. Render content with variables
        return self.render_prompt(content, variables, style)

    def render_prompt(
        self, template_content: str, variables: dict[str, Any], style: str = "f-string"
    ) -> str:
        """Render a template string with the provided variables.

        Args:
            template_content: The raw template text.
            variables: Key-value variables to format the template with.
            style: Formatting style ("f-string" or "template").

        Returns:
            The formatted prompt string.
        """
        if not variables:
            return template_content

        if style == "template":
            return Template(template_content).safe_substitute(variables)
        elif style == "f-string":
            result = template_content
            for key, val in variables.items():
                pattern = re.compile(r"\{" + re.escape(key) + r"\}")
                result = pattern.sub(str(val), result)
            return result
        else:
            raise ValueError(f"Unsupported formatting style: {style}")

    def _resolve_template_content(self, source: str) -> str:
        """Attempt to read source as a file path. If not found/not a file, treat as direct content."""
        # Check if source is a file path
        path = Path(source)
        if path.is_file():
            return path.read_text(encoding="utf-8")

        # Check relative to base_dir
        if self.base_dir:
            resolved_path = self.base_dir / source
            if resolved_path.is_file():
                return resolved_path.read_text(encoding="utf-8")

        # Otherwise treat as raw inline template content
        return source

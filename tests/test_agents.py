from src.agents.base import ImagePart, TextPart
from src.agents.prompt_manager import PromptManager


def test_prompt_manager_inline():
    """Test PromptManager loading and rendering inline template strings."""
    pm = PromptManager()

    # Test basic f-string style rendering
    prompt = pm.load_prompt("Hello {name}!", variables={"name": "Alice"})
    assert prompt == "Hello Alice!"

    # Test template style rendering
    prompt = pm.load_prompt("Hello $name!", variables={"name": "Bob"}, format_style="template")
    assert prompt == "Hello Bob!"

    # Test f-string safe dictionary (braces of JSON should not raise KeyError)
    prompt = pm.load_prompt(
        "Hello {name}! Literal: {not_provided} and JSON: {'key': 'val'}",
        variables={"name": "Alice"},
    )
    assert "Hello Alice!" in prompt
    assert "{not_provided}" in prompt
    assert "{'key': 'val'}" in prompt


def test_prompt_manager_file(tmp_path):
    """Test PromptManager loading templates from files."""
    # Create temp files
    system_file = tmp_path / "system.txt"
    system_file.write_text("System: {role}", encoding="utf-8")

    pm = PromptManager(base_dir=tmp_path)

    # Load file relative to base_dir
    prompt = pm.load_prompt("system.txt", variables={"role": "tester"})
    assert prompt == "System: tester"

    # Load direct absolute path
    prompt = pm.load_prompt(str(system_file), variables={"role": "architect"})
    assert prompt == "System: architect"


def test_agent_input_parts_representation(tmp_path):
    """Test multimodal AgentInputPart representations."""
    text_part = TextPart(text="hello world")
    assert text_part.text == "hello world"

    img_path = tmp_path / "test.png"
    img_path.write_bytes(b"image bytes")
    img_part = ImagePart.from_file(str(img_path), mime_type="image/png")
    assert img_part.path == img_path
    assert img_part.mime_type == "image/png"

    img_bytes_part = ImagePart.from_bytes(b"raw data", mime_type="image/jpeg")
    assert img_bytes_part.data == b"raw data"
    assert img_bytes_part.mime_type == "image/jpeg"

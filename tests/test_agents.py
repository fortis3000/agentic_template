from src.agents.base import FilePart, ImagePart, TextPart
from src.agents.config import AgentYamlConfig
from src.agents.contracts import AgentConfigProtocol
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


def test_file_part_and_config_contracts(tmp_path):
    """Test FilePart factory methods and AgentYamlConfig from_yaml and with_overrides."""
    doc_file = tmp_path / "sample.txt"
    doc_file.write_text("sample content", encoding="utf-8")

    file_part = FilePart.from_file(str(doc_file), mime_type="text/plain")
    assert file_part.path == doc_file
    assert file_part.filename == "sample.txt"

    file_bytes_part = FilePart.from_bytes(b"data", mime_type="text/plain", filename="test.txt")
    assert file_bytes_part.data == b"data"

    yaml_file = tmp_path / "agent.yaml"
    yaml_file.write_text(
        """
agent:
  name: "test_agent"
  model: "gemini-2.0-flash"
  provider: "google"
"""
    )
    cfg = AgentYamlConfig.from_yaml(yaml_file)
    assert cfg.agent.name == "test_agent"
    assert isinstance(cfg.agent, AgentConfigProtocol)

    updated = cfg.with_overrides(agent=cfg.agent.model_copy(update={"name": "renamed"}))
    assert updated.agent.name == "renamed"

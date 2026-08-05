from unittest.mock import MagicMock

import yaml

from src.agents.config import AgentConfigSchema, AgentYamlConfig, PhoenixConfigSchema

TEST_PORT = 6006
TEST_MAX_DIM = 1024
TEST_MIN_DIM = 128
TEST_MAX_FILE_BYTES = 20_971_520
TEST_MAX_FILES = 5
TEST_ATTEMPTS = 3


def test_phoenix_config_schema_defaults():
    config = PhoenixConfigSchema()
    assert config.enabled is True
    assert config.project_name == "agentic-template"
    assert config.collector_endpoint is None
    assert config.host is None
    assert config.port is None
    assert config.auto_instrument is True
    assert config.api_key is None


def test_phoenix_config_schema_custom():
    config = PhoenixConfigSchema(
        enabled=False,
        project_name="custom-project",
        collector_endpoint="http://localhost:6006/v1/traces",
        host="localhost",
        port=TEST_PORT,
        auto_instrument=False,
        api_key="secret-key",
    )
    assert config.enabled is False
    assert config.project_name == "custom-project"
    assert config.collector_endpoint == "http://localhost:6006/v1/traces"
    assert config.host == "localhost"
    assert config.port == TEST_PORT
    assert config.auto_instrument is False
    assert config.api_key == "secret-key"


def test_agent_yaml_config_with_phoenix_chapter(tmp_path):
    config_content = f"""
agent:
  name: "test_agent"
  model: "gemini-3.5-flash"

phoenix:
  enabled: true
  project_name: "my-phoenix-project"
  collector_endpoint: "http://phoenix-server:6006/v1/traces"
  host: "0.0.0.0"
  port: {TEST_PORT}
  auto_instrument: true
  api_key: "test-key"
"""
    yaml_file = tmp_path / "agent_config.yaml"
    yaml_file.write_text(config_content, encoding="utf-8")

    data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
    config = AgentYamlConfig.model_validate(data)

    assert config.agent.name == "test_agent"
    assert config.phoenix is not None
    assert config.phoenix.enabled is True
    assert config.phoenix.project_name == "my-phoenix-project"
    assert config.phoenix.collector_endpoint == "http://phoenix-server:6006/v1/traces"
    assert config.phoenix.host == "0.0.0.0"
    assert config.phoenix.port == TEST_PORT
    assert config.phoenix.auto_instrument is True
    assert config.phoenix.api_key == "test-key"


def test_agent_yaml_config_without_phoenix_chapter(tmp_path):
    config_content = """
agent:
  name: "test_agent"
  model: "gemini-3.5-flash"
"""
    yaml_file = tmp_path / "agent_config.yaml"
    yaml_file.write_text(config_content, encoding="utf-8")

    data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
    config = AgentYamlConfig.model_validate(data)

    assert config.agent.name == "test_agent"
    assert config.phoenix is None


def test_agent_config_schema_nested_phoenix():
    config = AgentConfigSchema(
        name="test_agent",
        phoenix=PhoenixConfigSchema(
            project_name="nested-phoenix",
            collector_endpoint="http://localhost:4317",
        ),
    )
    assert config.phoenix is not None
    assert config.phoenix.project_name == "nested-phoenix"
    assert config.phoenix.collector_endpoint == "http://localhost:4317"


def test_agent_config_constraints():
    config = AgentConfigSchema(name="test_agent")
    img = config.image_constraints
    assert img.acceptable_data_types == ["image/png", "image/jpeg", "image/gif"]
    assert img.max_image_width == TEST_MAX_DIM
    assert img.max_image_height == TEST_MAX_DIM
    assert img.min_image_width == TEST_MIN_DIM
    assert img.min_image_height == TEST_MIN_DIM

    file_c = config.file_constraints
    assert file_c.acceptable_file_types == [
        "application/pdf",
        "text/plain",
        "text/markdown",
        "text/html",
    ]
    assert file_c.max_file_size_bytes == TEST_MAX_FILE_BYTES
    assert file_c.max_files_per_message == TEST_MAX_FILES


def test_agent_config_normalize_mcp_servers():
    data = {
        "name": "test_agent",
        "mcp_servers": [
            {"name": "server1", "type": "stdio", "command": "node"},
            {"type": "http", "url": "http://localhost:8080"},
        ],
    }
    config = AgentConfigSchema.model_validate(data)
    assert "server1" in config.mcp_servers
    assert config.mcp_servers["server1"].command == "node"
    assert "http" in config.mcp_servers
    assert config.mcp_servers["http"].url == "http://localhost:8080"


def test_agent_config_clean_retry():
    data = {"name": "test_agent", "retry": None}
    config = AgentConfigSchema.model_validate(data)
    assert config.retry is not None
    assert config.retry.attempts == TEST_ATTEMPTS


def test_agent_config_get_system_and_user_prompt(tmp_path):
    prompt_file = tmp_path / "sys_prompt.txt"
    prompt_file.write_text("Hello {name}", encoding="utf-8")

    pm = MagicMock()
    pm.load_prompt.return_value = "Hello Alice"

    config = AgentConfigSchema(
        name="test_agent",
        system_prompt_path=str(prompt_file),
        user_prompt="User query {query}",
    )

    sys_p = config.get_system_prompt(pm, variables={"name": "Alice"})
    assert sys_p == "Hello Alice"
    pm.load_prompt.assert_called_with(
        str(prompt_file), variables={"name": "Alice"}, format_style="f-string"
    )

    pm.load_prompt.return_value = "User query weather"
    user_p = config.get_user_prompt(pm, variables={"query": "weather"})
    assert user_p == "User query weather"

    empty_config = AgentConfigSchema(name="empty_agent")
    assert empty_config.get_system_prompt(pm) == ""
    assert empty_config.get_user_prompt(pm) == ""

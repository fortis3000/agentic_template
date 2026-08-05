import yaml

from src.agents.config import AgentConfigSchema, AgentYamlConfig, PhoenixConfigSchema

TEST_PORT = 6006


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

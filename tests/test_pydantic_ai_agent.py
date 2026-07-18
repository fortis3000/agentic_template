from typing import Any, cast

import pytest
from pydantic_ai import BinaryContent
from pydantic_ai.models.test import TestModel

from src.agents.base import AgentInputPart, ImagePart, TextPart
from src.agents.prompt_manager import PromptManager
from src.agents.pydantic_ai import PydanticAIAgent, PydanticAIAgentGenerator
from src.tools.base import BaseTool, ToolFactory


def test_prompt_manager_inline():
    """Test PromptManager loading and rendering inline template strings (same as base test)."""
    pm = PromptManager()
    prompt = pm.load_prompt("Hello {name}!", variables={"name": "Alice"})
    assert prompt == "Hello Alice!"


def test_agent_config_parsing(tmp_path):
    """Test loading configuration and creating a PydanticAIAgent from YAML config."""
    config_file = tmp_path / "agent_config.yaml"
    config_content = """
agent:
  name: "test_pydantic_agent"
  model: "gemini-2.0-flash"
  provider: "google"
  system_prompt: "System instruction for {role}"
  user_prompt: "User instruction for {query}"
  app_data_dir: "data"
  tools:
    - "custom_tool"
"""
    config_file.write_text(config_content, encoding="utf-8")

    def mock_tool():
        return "tool_ran"

    generator = PydanticAIAgentGenerator(prompt_base_dir=tmp_path)
    agent = cast(
        PydanticAIAgent,
        generator.create_agent(
            str(config_file),
            system_variables={"role": "reviewer"},
            tools_registry={"custom_tool": mock_tool},
        ),
    )

    # Check model resolving
    assert agent.agent.model.__class__.__name__ == "GoogleModel"
    assert hasattr(agent.agent.model, "model_name")
    assert getattr(agent.agent.model, "model_name") == "gemini-2.0-flash"
    assert agent.agent._system_prompts == ("System instruction for reviewer",)

    # Check tools registration
    # In Pydantic AI, registered tools are available under agent.list_tools() or similar.
    # We can inspect the length of tools list in the agent
    assert len(agent.agent._function_toolset.tools) == 1
    tool_func = agent.agent._function_toolset.tools["mock_tool"].function
    while hasattr(tool_func, "__wrapped__"):
        tool_func = tool_func.__wrapped__
    assert tool_func == mock_tool


@pytest.mark.asyncio
async def test_agent_call_mocked(tmp_path):
    """Test calling the PydanticAIAgent with a mocked model using Pydantic AI's TestModel."""
    config_file = tmp_path / "agent_config.yaml"
    config_file.write_text(
        """
agent:
  name: "test_agent"
  model: "gemini-2.0-flash"
  provider: "google"
  system_prompt: "System prompt"
  user_prompt: "User query: {query}"
""",
        encoding="utf-8",
    )

    generator = PydanticAIAgentGenerator(prompt_base_dir=tmp_path)
    agent = cast(PydanticAIAgent, generator.create_agent(str(config_file)))

    # Use Pydantic AI's built-in override mechanism with TestModel
    test_model = TestModel(custom_output_text="mocked text response")
    with agent.agent.override(model=test_model):
        # 1. Test async call
        response_text = await agent.call(inputs={"query": "test query"})
        assert response_text == "mocked text response"

        # 2. Test call_stream
        stream_chunks = []
        async for chunk in agent.call_stream(inputs="custom prompt string"):
            stream_chunks.append(chunk)

        # TestModel returns the custom_result_text as a single chunk during streaming
        assert len(stream_chunks) > 0
        assert "".join(stream_chunks) == "mocked text response"


def test_agent_call_sync_mocked(tmp_path):
    """Test calling the PydanticAIAgent synchronously using call_sync."""
    config_file = tmp_path / "agent_config.yaml"
    config_file.write_text(
        """
agent:
  name: "test_agent"
  model: "gemini-2.0-flash"
  provider: "google"
  system_prompt: "System prompt"
  user_prompt: "User query: {query}"
""",
        encoding="utf-8",
    )

    generator = PydanticAIAgentGenerator(prompt_base_dir=tmp_path)
    agent = cast(PydanticAIAgent, generator.create_agent(str(config_file)))

    test_model = TestModel(custom_output_text="mocked text response")
    with agent.agent.override(model=test_model):
        response_text_sync = agent.call_sync(inputs=cast(Any, {"query": "test query"}))
        assert response_text_sync == "mocked text response"


def test_agent_inputs_mapping(tmp_path):
    """Test mapping multimodal inputs to Pydantic AI primitives (BinaryContent)."""
    config_file = tmp_path / "agent_config.yaml"
    config_file.write_text(
        "agent: {name: 'test_agent', model: 'gemini-3.5-flash', provider: 'google'}",
        encoding="utf-8",
    )

    generator = PydanticAIAgentGenerator(prompt_base_dir=tmp_path)
    agent = cast(PydanticAIAgent, generator.create_agent(str(config_file)))

    # TextPart
    inputs_text: list[AgentInputPart] = [TextPart(text="hello")]
    prepared = agent._prepare_inputs(inputs_text)
    assert prepared == ["hello"]

    # ImagePart from path
    img_path = tmp_path / "test.png"
    img_path.write_bytes(b"image data")
    inputs_img_path: list[AgentInputPart] = [ImagePart.from_file(str(img_path))]
    prepared = agent._prepare_inputs(inputs_img_path)
    assert len(prepared) == 1
    assert isinstance(prepared[0], BinaryContent)
    assert prepared[0].media_type == "image/png"
    assert prepared[0].data == b"image data"

    # ImagePart from bytes
    inputs_img_bytes: list[AgentInputPart] = [
        ImagePart.from_bytes(b"data bytes", mime_type="image/jpeg")
    ]
    prepared = agent._prepare_inputs(inputs_img_bytes)
    assert len(prepared) == 1
    assert isinstance(prepared[0], BinaryContent)
    assert prepared[0].media_type == "image/jpeg"
    assert prepared[0].data == b"data bytes"


def test_agent_config_model_factory(tmp_path):
    """Test configuration based model selection and provider factory validation."""
    # 1. Test google provider configuration
    config_google = tmp_path / "config_google.yaml"
    config_google.write_text(
        """
agent:
  name: "google_agent"
  model: "gemini-2.5-flash"
  provider: "google"
""",
        encoding="utf-8",
    )
    generator = PydanticAIAgentGenerator(prompt_base_dir=tmp_path)
    agent = cast(PydanticAIAgent, generator.create_agent(str(config_google)))
    assert agent.agent.model.__class__.__name__ == "GoogleModel"
    assert hasattr(agent.agent.model, "model_name")
    assert getattr(agent.agent.model, "model_name") == "gemini-2.5-flash"

    # 2. Test openai provider configuration
    config_openai = tmp_path / "config_openai.yaml"
    config_openai.write_text(
        """
agent:
  name: "openai_agent"
  model: "gpt-4o"
  provider: "openai"
""",
        encoding="utf-8",
    )
    agent = cast(PydanticAIAgent, generator.create_agent(str(config_openai)))
    assert agent.agent.model.__class__.__name__ == "OpenAIChatModel"
    assert hasattr(agent.agent.model, "model_name")
    assert getattr(agent.agent.model, "model_name") == "gpt-4o"

    # 3. Test ollama provider configuration
    config_ollama = tmp_path / "config_ollama.yaml"
    config_ollama.write_text(
        """
agent:
  name: "ollama_agent"
  model: "llama3"
  provider: "ollama"
  base_url: "http://localhost:11434/v1"
""",
        encoding="utf-8",
    )
    agent = cast(PydanticAIAgent, generator.create_agent(str(config_ollama)))
    assert agent.agent.model.__class__.__name__ == "OllamaModel"
    assert hasattr(agent.agent.model, "model_name")
    assert getattr(agent.agent.model, "model_name") == "llama3"


def test_agent_tools_factory_loading(tmp_path):
    """Test loading tools dynamically from a YAML file in PydanticAIAgentGenerator."""
    expected_result = 15

    # 1. Register a test tool
    @ToolFactory.register("pydantic_test_tool")
    class PydanticTestTool(BaseTool):
        def __init__(self, multiplier: int):
            self.multiplier = multiplier

        def get_callable(self):
            def multiply_by_n(val: int) -> int:
                """Multiplies a value by n."""
                return val * self.multiplier

            return multiply_by_n

    # 2. Create tools YAML configuration
    tools_config = tmp_path / "tools_config.yaml"
    tools_config.write_text(
        """
tools:
  my_test_tool:
    type: "pydantic_test_tool"
    config:
      multiplier: 3
""",
        encoding="utf-8",
    )

    # 3. Create agent configuration
    agent_config = tmp_path / "agent_config.yaml"
    agent_config.write_text(
        """
agent:
  name: "test_tools_agent"
  model: "gemini-2.5-flash"
  provider: "google"
  tools:
    - "my_test_tool"
""",
        encoding="utf-8",
    )

    # 4. Generate agent using tools_config_path
    generator = PydanticAIAgentGenerator(prompt_base_dir=tmp_path)
    agent = cast(
        PydanticAIAgent,
        generator.create_agent(
            str(agent_config),
            tools_config_path=str(tools_config),
        ),
    )

    # 5. Verify the tool is registered and executes correctly
    assert len(agent.agent._function_toolset.tools) == 1
    tool_func = agent.agent._function_toolset.tools["multiply_by_n"].function
    if hasattr(tool_func, "__wrapped__"):
        tool_func = tool_func.__wrapped__
    assert callable(tool_func)
    assert cast(Any, tool_func)(5) == expected_result

import os
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.antigravity.types import McpStdioServer

from src.agents.base import AgentInputPart, ImagePart, TextPart
from src.agents.google_antigravity import AntigravityAgent, AntigravityAgentGenerator
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


def test_agent_config_parsing(tmp_path):
    """Test loading configuration and creating an agent from YAML config."""
    config_file = tmp_path / "agent_config.yaml"
    config_content = """
agent:
  name: "test_agent"
  model: "gemini-3.5-flash"
  system_prompt: "System instruction for {role}"
  user_prompt: "User instruction for {query}"
  app_data_dir: "data"
  tools:
    - "custom_tool"
  mcp_servers:
    filesystem:
      type: "stdio"
      command: "npx"
      args: ["-y", "@modelcontextprotocol/server-filesystem"]
"""
    config_file.write_text(config_content, encoding="utf-8")

    def mock_tool():
        pass

    generator = AntigravityAgentGenerator(prompt_base_dir=tmp_path)
    agent = cast(
        AntigravityAgent,
        generator.create_agent(
            str(config_file),
            system_variables={"role": "assistant"},
            tools_registry={"custom_tool": mock_tool},
        ),
    )
    assert isinstance(agent, AntigravityAgent)

    assert agent.config.model == "gemini-3.5-flash"
    assert agent.config.system_instructions == "System instruction for assistant"
    assert len(agent.config.tools) == 1
    assert getattr(agent.config.tools[0], "__wrapped__", agent.config.tools[0]) == mock_tool
    assert len(agent.config.mcp_servers) == 1
    server = agent.config.mcp_servers[0]
    assert isinstance(server, McpStdioServer)
    assert server.name == "filesystem"
    assert server.command == "npx"
    app_dir = agent.config.app_data_dir
    assert app_dir is not None
    assert os.path.isabs(app_dir)


@pytest.mark.asyncio
async def test_agent_call_mocked(tmp_path):
    """Test calling the agent with mocked Google Antigravity SDK client."""
    config_file = tmp_path / "agent_config.yaml"
    config_file.write_text(
        """
agent:
  name: "test_agent"
  model: "gemini-3.5-flash"
  system_prompt: "System prompt"
  user_prompt: "User query: {query}"
""",
        encoding="utf-8",
    )

    generator = AntigravityAgentGenerator(prompt_base_dir=tmp_path)
    agent = cast(AntigravityAgent, generator.create_agent(str(config_file)))

    # Mock the G_Agent context manager and response
    mock_response = AsyncMock()
    mock_response.text = AsyncMock(return_value="mocked text response")

    # Mock async iterator for streaming
    async def mock_aiter_fn():
        yield "chunk1"
        yield "chunk2"

    class AsyncIterWrapper:
        def __aiter__(self):
            return mock_aiter_fn()

    mock_stream_response = MagicMock()
    mock_stream_response.__aiter__ = lambda x: mock_aiter_fn()

    # Set up G_Agent patch
    with patch("src.agents.google_antigravity.G_Agent") as mock_g_agent:
        mock_instance = AsyncMock()
        mock_g_agent.return_value.__aenter__.return_value = mock_instance

        # 1. Test call (non-streaming)
        mock_instance.chat.return_value = mock_response
        response_text = await agent.call(inputs={"query": "test query"})
        assert response_text == "mocked text response"
        mock_instance.chat.assert_called_once_with(["User query: test query"])

        # 2. Test call_stream (streaming)
        mock_instance.chat.reset_mock()
        mock_instance.chat.return_value = mock_stream_response
        stream_chunks = []
        async for chunk in agent.call_stream(inputs="custom prompt string"):
            stream_chunks.append(chunk)

        assert stream_chunks == ["chunk1", "chunk2"]
        mock_instance.chat.assert_called_once_with(["custom prompt string"])


def test_agent_inputs_mapping(tmp_path):
    """Test mapping multimodal inputs to Antigravity primitives."""
    config_file = tmp_path / "agent_config.yaml"
    config_file.write_text("agent: {name: 'test_agent'}", encoding="utf-8")

    generator = AntigravityAgentGenerator(prompt_base_dir=tmp_path)
    agent = cast(AntigravityAgent, generator.create_agent(str(config_file)))

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
    assert prepared[0].mime_type == "image/png"
    assert prepared[0].data == b"image data"

    # ImagePart from bytes
    inputs_img_bytes: list[AgentInputPart] = [
        ImagePart.from_bytes(b"data bytes", mime_type="image/jpeg")
    ]
    prepared = agent._prepare_inputs(inputs_img_bytes)
    assert len(prepared) == 1
    assert prepared[0].mime_type == "image/jpeg"
    assert prepared[0].data == b"data bytes"

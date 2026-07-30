import asyncio
import os
import time
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import phoenix as px
import yaml
from phoenix.otel import register

from src.agents.config import AgentYamlConfig, PhoenixConfigSchema
from src.agents.google_antigravity import AntigravityAgent, AntigravityAgentGenerator
from src.tools.qdrant_db import QdrantVectorDB
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _load_phoenix_config(
    config_path: str = "configs/agent_config.yaml",
) -> PhoenixConfigSchema | None:
    """Loads Phoenix configuration parameters from YAML config if available."""
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if data:
                parsed = AgentYamlConfig.model_validate(data)
                return parsed.phoenix or (parsed.agent.phoenix if parsed.agent else None)
        except Exception as e:
            logger.warning(f"Could not load phoenix config from {config_path}: {e}")
    return None


def get_weather(location: str) -> str:
    """Gets the current weather for a location."""
    logger.info(f"[Tool: get_weather] Executing for location: {location}")
    return f"The weather in {location} is sunny and 22°C."


async def run_live_demo_run(agent: AntigravityAgent, query: str) -> None:
    """Runs a live agent session with actual API keys to generate traces."""
    logger.info("Running live agent run...")
    try:
        # First, trigger the weather tool directly to make sure a tool span is generated
        tool_func = agent.config.tools[0]
        logger.info("Invoking registered tool...")
        tool_func(location="Paris")

        # Then run agent call
        response = await agent.call(inputs={"query": query})
        logger.info(f"Agent Response: {response}")
    except Exception as e:
        logger.error(f"Error during live agent run: {e}")


async def run_mocked_demo_run(agent: AntigravityAgent, query: str) -> None:
    """Runs a mocked agent session to generate traces without making API requests."""
    logger.info("Running with mocked agent and tool calls to generate traces...")
    # Mock G_Agent context manager and response
    mock_response = AsyncMock()
    mock_response.text = AsyncMock(
        return_value="According to the get_weather tool, the weather in Paris is sunny and 22°C."
    )

    with patch("src.agents.google_antigravity.G_Agent") as mock_g_agent:
        mock_instance = AsyncMock()
        mock_g_agent.return_value.__aenter__.return_value = mock_instance
        mock_instance.chat.return_value = mock_response

        # Call the wrapped tool to generate a tool span
        logger.info("Simulating tool call...")
        wrapped_tool = agent.config.tools[0]
        wrapped_tool(location="Paris")

        # Call the agent
        response = await agent.call(inputs={"query": query})
        logger.info(f"Mocked Agent Response: {response}")


async def run_demo_agent_run():
    """Runs a demo agent run, instrumented by OpenTelemetry, to send traces to Phoenix."""
    logger.info("Spawning Agentic Session")

    # 1. Initialize the agent generator
    generator = AntigravityAgentGenerator(prompt_base_dir="src/prompts")

    # 2. Create the agent from configs/agent_config.yaml
    config_path = "configs/agent_config.yaml"
    if not os.path.exists(config_path):
        logger.error(f"Error: agent config '{config_path}' not found.")
        return

    # Use a dummy system variable role
    agent = cast(
        AntigravityAgent,
        generator.create_agent(
            config_path,
            system_variables={"role": "Weather Assistant"},
            tools_registry={"get_weather": get_weather},
        ),
    )

    query = "Check the weather in Paris."
    logger.info(f"Running agent query: '{query}'")

    has_api_key = os.getenv("GEMINI_API_KEY") is not None
    if has_api_key:
        await run_live_demo_run(agent, query)
    else:
        await run_mocked_demo_run(agent, query)

    # 4. Generate a dummy VectorDB span to demonstrate VectorDB tracing
    try:
        logger.info("Simulating VectorDB search to generate retriever span...")
        db = QdrantVectorDB(location=":memory:")
        await db.create_collection("demo_collection", vector_size=4)
        await db.insert(
            "demo_collection",
            ids=[1],
            vectors=[[0.1, 0.2, 0.3, 0.4]],
            payloads=[{"text": "Sample document"}],
        )
        await db.search(
            "demo_collection", query_vector=[0.1, 0.2, 0.3, 0.4], limit=1, query_text="Search query"
        )
        logger.info("VectorDB search simulated successfully!")
    except Exception as db_err:
        logger.warning(f"Failed to simulate VectorDB search: {db_err}")

    logger.info("Spans successfully generated and sent to Arize Phoenix collector!")


def _get_launch_kwargs(phoenix_config: PhoenixConfigSchema | None) -> dict[str, Any]:
    """Builds keyword arguments for px.launch_app from phoenix config."""
    kwargs: dict[str, Any] = {}
    if phoenix_config and phoenix_config.host:
        kwargs["host"] = phoenix_config.host
    if phoenix_config and phoenix_config.port:
        kwargs["port"] = phoenix_config.port
    return kwargs


def _wait_for_shutdown(session_url: str) -> None:
    """Keeps the service running locally until user input or interrupt."""
    logger.info("Arize Phoenix is now active.")
    logger.info(f"Open your browser and navigate to: {session_url}")
    try:
        input("\nPress Enter to stop the Arize Phoenix service and exit...\n")
    except (EOFError, KeyboardInterrupt):
        logger.info("Non-interactive session detected or interrupted.")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
    logger.info("Stopping Arize Phoenix...")


def main():
    logger.info("Starting Arize Phoenix Observability Service...")

    phoenix_config = _load_phoenix_config("configs/agent_config.yaml")

    collector_endpoint = os.getenv("PHOENIX_COLLECTOR_ENDPOINT") or (
        phoenix_config.collector_endpoint if phoenix_config else None
    )
    project_name = (
        phoenix_config.project_name
        if phoenix_config and phoenix_config.project_name
        else "agentic-template"
    )
    auto_instrument = (
        phoenix_config.auto_instrument
        if phoenix_config and phoenix_config.auto_instrument is not None
        else True
    )

    session_url = None

    if collector_endpoint:
        logger.info(f"Collector endpoint is set to {collector_endpoint}.")
        logger.info(
            "Skipping local launch_app() and sending traces directly to the configured collector."
        )
    else:
        session = px.launch_app(**_get_launch_kwargs(phoenix_config))
        if session:
            logger.info(f"Phoenix UI and OTLP Collector are running at: {session.url}")
            session_url = session.url

    register(
        project_name=project_name,
        endpoint=collector_endpoint,
        auto_instrument=auto_instrument,
    )
    logger.info(f"OpenTelemetry global Tracer Provider registered (project: '{project_name}').")

    try:
        asyncio.run(run_demo_agent_run())
    except Exception as e:
        logger.error(f"Failed to execute demo agent run: {e}")

    if not collector_endpoint and session_url:
        _wait_for_shutdown(session_url)
    else:
        logger.info("Traces successfully sent to the configured collector.")


if __name__ == "__main__":
    main()

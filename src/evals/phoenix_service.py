import asyncio
import os
import time
from typing import cast
from unittest.mock import AsyncMock, patch

import phoenix as px
from phoenix.otel import register

from src.agents.google_antigravity import AntigravityAgent, AntigravityAgentGenerator
from src.utils.logger import get_logger

logger = get_logger(__name__)


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

    logger.info("Spans successfully generated and sent to Arize Phoenix collector!")


def main():
    logger.info("Starting Arize Phoenix Observability Service...")

    collector_endpoint = os.getenv("PHOENIX_COLLECTOR_ENDPOINT")
    session_url = None

    if collector_endpoint:
        logger.info(f"PHOENIX_COLLECTOR_ENDPOINT is set to {collector_endpoint}.")
        logger.info(
            "Skipping local launch_app() and sending traces directly to the configured collector."
        )
    else:
        # 1. Launch Phoenix application
        # By default, this starts the collector server (typically on http://localhost:6006)
        session = px.launch_app()
        if session:
            logger.info(f"Phoenix UI and OTLP Collector are running at: {session.url}")
            session_url = session.url

    # 2. Register OpenTelemetry Tracer Provider with Phoenix-aware defaults
    # Uses PHOENIX_COLLECTOR_ENDPOINT env var if set, otherwise defaults to localhost:4317
    register(
        project_name="agentic-template",
        auto_instrument=True,
    )
    logger.info("OpenTelemetry global Tracer Provider registered.")

    # 3. Run a quick demo agent session to populate the dashboard with traces
    try:
        asyncio.run(run_demo_agent_run())
    except Exception as e:
        logger.error(f"Failed to execute demo agent run: {e}")

    # 4. Keep the service running (only if we launched it locally)
    if not collector_endpoint and session_url:
        logger.info("Arize Phoenix is now active.")
        logger.info(f"Open your browser and navigate to: {session_url}")

        try:
            input("\nPress Enter to stop the Arize Phoenix service and exit...\n")
        except EOFError:
            logger.info(
                "Non-interactive session detected. Keep running until interrupted (Ctrl+C)..."
            )

            try:
                while True:
                    time.sleep(3600)
            except KeyboardInterrupt:
                pass
        except KeyboardInterrupt:
            pass

        logger.info("Stopping Arize Phoenix...")
    else:
        logger.info("Traces successfully sent to the configured collector.")


if __name__ == "__main__":
    main()

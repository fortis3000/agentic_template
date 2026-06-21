import asyncio
import os
from unittest.mock import AsyncMock, patch

import phoenix as px
from phoenix.otel import register

from src.agents.google_antigravity import AntigravityAgentGenerator


def get_weather(location: str) -> str:
    """Gets the current weather for a location."""
    print(f"[Tool: get_weather] Executing for location: {location}")
    return f"The weather in {location} is sunny and 22°C."


async def run_demo_agent_run():
    """Runs a demo agent run, instrumented by OpenTelemetry, to send traces to Phoenix."""
    print("\n--- Spawning Agentic Session ---")
    
    # 1. Initialize the agent generator
    generator = AntigravityAgentGenerator(prompt_base_dir="src/prompts")
    
    # 2. Create the agent from configs/agent_config.yaml
    config_path = "configs/agent_config.yaml"
    if not os.path.exists(config_path):
        print(f"Error: agent config '{config_path}' not found.")
        return

    # Use a dummy system variable role
    agent = generator.create_agent(
        config_path,
        system_variables={"role": "Weather Assistant"},
        tools_registry={"get_weather": get_weather}
    )

    query = "Check the weather in Paris."
    print(f"Running agent query: '{query}'")

    has_api_key = os.getenv("GEMINI_API_KEY") is not None
    if has_api_key:
        print("Running live agent run...")
        try:
            # First, trigger the weather tool directly to make sure a tool span is generated
            tool_func = agent.config.tools[0]
            print("Invoking registered tool...")
            tool_func(location="Paris")

            # Then run agent call
            response = await agent.call(inputs={"query": query})
            print("\n--- Agent Response ---")
            print(response)
        except Exception as e:
            print(f"Error during live agent run: {e}")
    else:
        print("GEMINI_API_KEY not found. Running with mocked agent and tool calls to generate traces...")
        # Mock G_Agent context manager and response
        mock_response = AsyncMock()
        mock_response.text = AsyncMock(return_value="According to the get_weather tool, the weather in Paris is sunny and 22°C.")
        
        with patch("src.agents.google_antigravity.G_Agent") as mock_g_agent:
            mock_instance = AsyncMock()
            mock_g_agent.return_value.__aenter__.return_value = mock_instance
            mock_instance.chat.return_value = mock_response

            # Call the wrapped tool to generate a tool span
            print("Simulating tool call...")
            wrapped_tool = agent.config.tools[0]
            wrapped_tool(location="Paris")

            # Call the agent
            response = await agent.call(inputs={"query": query})
            print("\n--- Mocked Agent Response ---")
            print(response)

    print("\nSpans successfully generated and sent to Arize Phoenix collector!")


def main():
    print("==================================================")
    print("Starting Arize Phoenix Observability Service...")
    print("==================================================")

    # 1. Launch Phoenix application
    # By default, this starts the collector server (typically on http://localhost:6006)
    session = px.launch_app()
    print(f"\nPhoenix UI and OTLP Collector are running at: {session.url}")

    # 2. Register OpenTelemetry Tracer Provider with Phoenix-aware defaults
    # Uses PHOENIX_COLLECTOR_ENDPOINT env var if set, otherwise defaults to localhost:4317
    register(
        project_name="agentic-template",
        auto_instrument=True,
    )
    print("OpenTelemetry global Tracer Provider registered.")

    # 3. Run a quick demo agent session to populate the dashboard with traces
    try:
        asyncio.run(run_demo_agent_run())
    except Exception as e:
        print(f"Failed to execute demo agent run: {e}")

    # 4. Keep the service running
    print("\n" + "=" * 50)
    print("Arize Phoenix is now active.")
    print(f"Open your browser and navigate to: {session.url}")
    print("=" * 50)
    
    try:
        input("\nPress Enter to stop the Arize Phoenix service and exit...\n")
    except KeyboardInterrupt:
        pass
    
    print("Stopping Arize Phoenix...")


if __name__ == "__main__":
    main()

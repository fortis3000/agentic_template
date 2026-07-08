import asyncio
from typing import cast

from dotenv import load_dotenv

from src.agents.pydantic_ai import PydanticAIAgent, PydanticAIAgentGenerator
from src.utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)


def get_weather(location: str) -> str:
    """Gets the current weather for a location."""
    logger.info(f"[Tool: get_weather] Executing for location: {location}")
    return f"The weather in {location} is sunny and 24°C."


async def main():
    logger.info("Initializing PydanticAIAgentGenerator...")
    # 1. Initialize Pydantic AI agent generator
    generator = PydanticAIAgentGenerator(prompt_base_dir="src/prompts")

    # 2. Create the agent from YAML config
    # Note: Ensure GEMINI_API_KEY, GOOGLE_API_KEY, or OPENAI_API_KEY is configured in your .env
    config_path = "configs/agent_config.yaml"
    logger.info(f"Loading agent config from {config_path}...")

    agent = cast(
        PydanticAIAgent,
        generator.create_agent(
            config_path,
            system_variables={"role": "Senior Weather Specialist"},
            tools_registry={"get_weather": get_weather},
        ),
    )

    query = "Check the weather in Paris, and write a one-sentence response."
    logger.info(f"Sending Query to Agent: '{query}'")

    # 3. Call the agent (non-streaming)
    try:
        response = await agent.call(inputs={"query": query})
        logger.info("--- Agent Response ---")
        logger.info(response)
    except Exception as e:
        logger.error(f"Failed to execute agent call: {e}")

    # 4. Stream call
    logger.info("--- Streaming Response ---")
    try:
        chunks = []
        async for chunk in agent.call_stream(inputs="Tell me a joke about Python."):
            chunks.append(chunk)
        logger.info("".join(chunks))
    except Exception as e:
        logger.error(f"Failed to stream: {e}")


if __name__ == "__main__":
    asyncio.run(main())

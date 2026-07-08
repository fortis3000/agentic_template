import asyncio
import os
import tempfile
from typing import cast

from dotenv import load_dotenv

from src.agents.pydantic_ai import PydanticAIAgent, PydanticAIAgentGenerator
from src.utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)


def dummy_tool(topic: str) -> str:
    """A dummy tool to test tool calling capability."""
    logger.info(f"[Tool: dummy_tool] Executing for topic: {topic}")
    return f"Information about {topic} resolved successfully."


async def main():
    logger.info("Initializing PydanticAIAgentGenerator...")
    generator = PydanticAIAgentGenerator(prompt_base_dir="src/prompts")

    # Create a temporary config for the Ollama agent
    with tempfile.NamedTemporaryFile(
        suffix=".yaml", mode="w", delete=False, encoding="utf-8"
    ) as tmp:
        config_content = """
agent:
  name: "ollama_test_agent"
  model: "qwen3.5:4b"
  provider: "ollama"
  base_url: "http://localhost:11434/v1"
  system_prompt_path: "src/prompts/system_prompt.txt"
  user_prompt_path: "src/prompts/user_prompt.txt"
  tools:
    - "dummy_tool"
"""
        tmp.write(config_content)
        config_path = tmp.name

    try:
        logger.info(f"Creating Ollama agent from config: {config_path}")
        agent = cast(
            PydanticAIAgent,
            generator.create_agent(
                config_path,
                system_variables={"role": "Local AI Assistant"},
                tools_registry={"dummy_tool": dummy_tool},
            ),
        )

        logger.info(f"Ollama Agent Model Class: {agent.agent.model.__class__.__name__}")
        logger.info(f"Ollama Agent Model Name: {getattr(agent.agent.model, 'model_name', None)}")

        query = (
            "Explain what a neural network is in one short sentence, and verify dummy_tool works."
        )
        logger.info(f"Sending query: '{query}'")

        try:
            response = await agent.call(inputs={"query": query})
            logger.info("--- Ollama Response ---")
            logger.info(response)
        except Exception as e:
            logger.error(
                f"Failed to run agent. Make sure Ollama is running locally (e.g. `ollama run llama3.2`) "
                f"or OLLAMA_BASE_URL is configured properly. Error details: {e}"
            )

    finally:
        os.unlink(config_path)


if __name__ == "__main__":
    asyncio.run(main())

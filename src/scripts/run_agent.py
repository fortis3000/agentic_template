import asyncio
from typing import cast

from dotenv import load_dotenv

from src.agents import PydanticAIAgent, PydanticAIAgentGenerator
from src.utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)


async def main():
    # 1. Initialize the agent generator
    generator = PydanticAIAgentGenerator(prompt_base_dir="src/prompts")

    # 2. Create the agent from YAML config, supplying system prompt variables dynamically
    agent = cast(
        PydanticAIAgent,
        generator.create_agent(
            "configs/agent_config.yaml", system_variables={"role": "Senior AI Architect"}
        ),
    )

    # 3. Call the agent (non-streaming)
    # Supplying a dictionary will format the default user prompt from the config
    response = await agent.call(inputs={"query": "Explain quantum computing in one sentence."})
    logger.info("--- Non-streaming Response ---")
    logger.info(response)

    # 4. Call the agent (streaming)
    logger.info("--- Streaming Response ---")
    chunks = []
    async for chunk in agent.call_stream(inputs="Tell me a joke about Python."):
        chunks.append(chunk)
    logger.info("".join(chunks))

    # 5. Multimodal Call (Text and Image)
    # image = ImagePart.from_file("data/raw/example.png")
    # response = await agent.call(inputs=["Describe this image", image])


if __name__ == "__main__":
    asyncio.run(main())

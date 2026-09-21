"""Leaf contracts package for agents with zero internal dependencies."""

from src.agents.contracts.agent import AgentRunnerProtocol
from src.agents.contracts.config import AgentConfigProtocol

__all__ = [
    "AgentConfigProtocol",
    "AgentRunnerProtocol",
]

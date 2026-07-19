import asyncio
import os
from abc import ABC, abstractmethod
from typing import Any, cast

from google import genai
from google.genai import types
from openai import AsyncOpenAI
from pydantic import BaseModel, model_validator

from src.agents.config import EmbeddingModelConfigSchema
from src.utils.logger import get_logger

logger = get_logger(__name__)


class EmbeddingResponse(BaseModel):
    embedding: list[float]
    dimensions: int
    model_name: str

    @model_validator(mode="after")
    def validate_embedding(self) -> "EmbeddingResponse":
        if not self.embedding:
            raise ValueError("Embedding list cannot be empty.")
        if not all(isinstance(x, (int, float)) for x in self.embedding):
            raise ValueError("Embedding must contain only numeric values.")
        # Normalize elements to float
        self.embedding = [float(x) for x in self.embedding]
        if len(self.embedding) != self.dimensions:
            raise ValueError(
                f"Embedding length {len(self.embedding)} does not match expected dimensions {self.dimensions}"
            )
        return self


class BatchEmbeddingResponse(BaseModel):
    embeddings: list[list[float]]
    dimensions: int
    model_name: str

    @model_validator(mode="after")
    def validate_embeddings(self) -> "BatchEmbeddingResponse":
        if not self.embeddings:
            raise ValueError("Embeddings batch list cannot be empty.")
        for i, emb in enumerate(self.embeddings):
            if not emb:
                raise ValueError(f"Embedding at index {i} cannot be empty.")
            if not all(isinstance(x, (int, float)) for x in emb):
                raise ValueError(f"Embedding at index {i} must contain only numeric values.")
            self.embeddings[i] = [float(x) for x in emb]
            if len(emb) != self.dimensions:
                raise ValueError(
                    f"Embedding at index {i} length {len(emb)} does not match expected dimensions {self.dimensions}"
                )
        return self


class BaseEmbeddingClient(ABC):
    """Abstract base class for generating text and image embeddings."""

    def __init__(self, config: EmbeddingModelConfigSchema):
        self.config = config

    @abstractmethod
    async def embed_text(self, text: str) -> EmbeddingResponse:
        """Asynchronously generate embedding for text."""
        pass

    @abstractmethod
    async def embed_image(self, image_bytes: bytes, mime_type: str) -> EmbeddingResponse:
        """Asynchronously generate embedding for an image."""
        pass

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> BatchEmbeddingResponse:
        """Asynchronously generate embeddings for a batch of text inputs."""
        pass


class GoogleEmbeddingClient(BaseEmbeddingClient):
    """Google Gemini GenAI embedding client."""

    def __init__(self, config: EmbeddingModelConfigSchema):
        super().__init__(config)
        api_key = (
            config.api_key
            or os.getenv("GEMINI_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
            or "placeholder_key"
        )
        # Google GenAI Client uses sync calls under the hood, but we wrap in a thread or call standard methods.
        self.client = genai.Client(api_key=api_key)

    async def embed_text(self, text: str) -> EmbeddingResponse:
        logger.info(f"Generating Google embedding for text (model: {self.config.model})...")
        # Run synchronous call in thread pool to prevent blocking event loop
        loop = asyncio.get_running_loop()
        raw_response = await loop.run_in_executor(
            None,
            lambda: self.client.models.embed_content(
                model=self.config.model,
                contents=text,
            ),
        )
        response: Any = raw_response
        # response.embedding.values contains the floats
        if (
            not hasattr(response, "embedding")
            or not response.embedding
            or not response.embedding.values
        ):
            raise ValueError("No embedding returned from Google API.")

        values = response.embedding.values
        dims = self.config.dimensions or len(values)
        return EmbeddingResponse(
            embedding=values,
            dimensions=dims,
            model_name=self.config.model,
        )

    async def embed_image(self, image_bytes: bytes, mime_type: str) -> EmbeddingResponse:
        logger.info(f"Generating Google embedding for image (model: {self.config.model})...")
        if "multimodal" not in self.config.model.lower():
            raise ValueError(
                f"Model '{self.config.model}' does not support multimodal/image inputs."
            )

        loop = asyncio.get_running_loop()
        part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        raw_response = await loop.run_in_executor(
            None,
            lambda: self.client.models.embed_content(
                model=self.config.model,
                contents=part,
            ),
        )
        response: Any = raw_response
        if (
            not hasattr(response, "embedding")
            or not response.embedding
            or not response.embedding.values
        ):
            raise ValueError("No embedding returned from Google API.")

        values = response.embedding.values
        dims = self.config.dimensions or len(values)
        return EmbeddingResponse(
            embedding=values,
            dimensions=dims,
            model_name=self.config.model,
        )

    async def embed_batch(self, texts: list[str]) -> BatchEmbeddingResponse:
        logger.info(f"Generating Google embeddings for batch of {len(texts)} texts...")
        loop = asyncio.get_running_loop()
        raw_response = await loop.run_in_executor(
            None,
            lambda: self.client.models.embed_content(
                model=self.config.model,
                contents=cast(Any, texts),
            ),
        )
        response: Any = raw_response
        # For batches, response.embeddings is a list of ContentEmbedding objects
        if not response.embeddings:
            raise ValueError("No embeddings returned from Google API batch request.")

        embeddings_list: list[list[float]] = [
            emb.values for emb in response.embeddings if emb and emb.values is not None
        ]
        if not embeddings_list:
            raise ValueError("Empty batch embeddings returned from Google API.")

        dims = self.config.dimensions or len(embeddings_list[0])
        return BatchEmbeddingResponse(
            embeddings=embeddings_list,
            dimensions=dims,
            model_name=self.config.model,
        )


class OpenAIEmbeddingClient(BaseEmbeddingClient):
    """OpenAI embedding client."""

    def __init__(self, config: EmbeddingModelConfigSchema):
        super().__init__(config)
        api_key = config.api_key or os.getenv("OPENAI_API_KEY") or "placeholder_key"
        self.client = AsyncOpenAI(api_key=api_key, base_url=config.base_url)

    async def embed_text(self, text: str) -> EmbeddingResponse:
        logger.info(f"Generating OpenAI embedding for text (model: {self.config.model})...")
        response = await self.client.embeddings.create(
            input=text,
            model=self.config.model,
        )
        values = response.data[0].embedding
        dims = self.config.dimensions or len(values)
        return EmbeddingResponse(
            embedding=values,
            dimensions=dims,
            model_name=self.config.model,
        )

    async def embed_image(self, image_bytes: bytes, mime_type: str) -> EmbeddingResponse:
        # OpenAI text embedding models do not support image inputs
        raise ValueError(f"Model '{self.config.model}' does not support multimodal/image inputs.")

    async def embed_batch(self, texts: list[str]) -> BatchEmbeddingResponse:
        logger.info(f"Generating OpenAI embeddings for batch of {len(texts)} texts...")
        response = await self.client.embeddings.create(
            input=texts,
            model=self.config.model,
        )
        embeddings_list = [item.embedding for item in response.data]
        dims = self.config.dimensions or len(embeddings_list[0])
        return BatchEmbeddingResponse(
            embeddings=embeddings_list,
            dimensions=dims,
            model_name=self.config.model,
        )


class EmbeddingModelFactory:
    """Factory to create embedding model clients."""

    @staticmethod
    def create(config: EmbeddingModelConfigSchema) -> BaseEmbeddingClient:
        provider = config.provider.lower().strip()
        if provider == "google":
            return GoogleEmbeddingClient(config)
        elif provider == "openai":
            return OpenAIEmbeddingClient(config)
        else:
            raise ValueError(f"Unsupported embedding provider: '{config.provider}'")

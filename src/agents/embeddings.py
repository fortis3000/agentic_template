import asyncio
import os
from abc import ABC, abstractmethod
from typing import Any, cast

import httpx
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
        embed_kwargs: dict[str, Any] = {
            "model": self.config.model,
            "contents": text,
        }
        if self.config.dimensions:
            embed_kwargs["config"] = types.EmbedContentConfig(
                output_dimensionality=self.config.dimensions
            )
        raw_response = await loop.run_in_executor(
            None,
            lambda: self.client.models.embed_content(**embed_kwargs),
        )
        response: Any = raw_response
        # response.embeddings[0].values contains the floats
        if (
            not hasattr(response, "embeddings")
            or not response.embeddings
            or not response.embeddings[0].values
        ):
            raise ValueError("No embedding returned from Google API.")

        values = response.embeddings[0].values
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
        embed_kwargs: dict[str, Any] = {
            "model": self.config.model,
            "contents": part,
        }
        if self.config.dimensions:
            embed_kwargs["config"] = types.EmbedContentConfig(
                output_dimensionality=self.config.dimensions
            )
        raw_response = await loop.run_in_executor(
            None,
            lambda: self.client.models.embed_content(**embed_kwargs),
        )
        response: Any = raw_response
        if (
            not hasattr(response, "embeddings")
            or not response.embeddings
            or not response.embeddings[0].values
        ):
            raise ValueError("No embedding returned from Google API.")

        values = response.embeddings[0].values
        dims = self.config.dimensions or len(values)
        return EmbeddingResponse(
            embedding=values,
            dimensions=dims,
            model_name=self.config.model,
        )

    async def embed_batch(self, texts: list[str]) -> BatchEmbeddingResponse:
        logger.info(f"Generating Google embeddings for batch of {len(texts)} texts...")
        loop = asyncio.get_running_loop()
        embed_kwargs: dict[str, Any] = {
            "model": self.config.model,
            "contents": cast(Any, texts),
        }
        if self.config.dimensions:
            embed_kwargs["config"] = types.EmbedContentConfig(
                output_dimensionality=self.config.dimensions
            )
        raw_response = await loop.run_in_executor(
            None,
            lambda: self.client.models.embed_content(**embed_kwargs),
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
        if len(embeddings_list) != len(texts):
            raise ValueError(
                f"Embedding count mismatch: requested {len(texts)}, "
                f"received {len(embeddings_list)}. Some inputs may have been dropped by the API."
            )

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


class OllamaEmbeddingClient(BaseEmbeddingClient):
    """Ollama embedding client using raw HTTP calls."""

    def __init__(self, config: EmbeddingModelConfigSchema):
        super().__init__(config)
        self.base_url = config.base_url or os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434"

    async def embed_text(self, text: str) -> EmbeddingResponse:
        logger.info(f"Generating Ollama embedding for text (model: {self.config.model})...")
        if "text" not in self.config.supported_data_types:
            raise ValueError(
                "Ollama embedding client does not support 'text' input based on config."
            )

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/api/embeddings",
                json={
                    "model": self.config.model,
                    "prompt": text,
                },
            )
            response.raise_for_status()
            data = response.json()
            values = data["embedding"]
            dims = self.config.dimensions or len(values)
            # Validate that dimensions match if specified in config
            if self.config.dimensions and len(values) != self.config.dimensions:
                raise ValueError(
                    f"Ollama model '{self.config.model}' returned embedding of size {len(values)}, "
                    f"which does not match the configured dimensions {self.config.dimensions}."
                )

            return EmbeddingResponse(
                embedding=values,
                dimensions=dims,
                model_name=self.config.model,
            )

    async def embed_image(self, image_bytes: bytes, mime_type: str) -> EmbeddingResponse:
        raise ValueError("Ollama local embedding models do not support multimodal/image inputs.")

    async def embed_batch(self, texts: list[str]) -> BatchEmbeddingResponse:
        logger.info(f"Generating Ollama embeddings for batch of {len(texts)} texts...")
        tasks = [self.embed_text(t) for t in texts]
        results = await asyncio.gather(*tasks)
        embeddings_list = [r.embedding for r in results]
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
        elif provider == "ollama":
            return OllamaEmbeddingClient(config)
        else:
            raise ValueError(f"Unsupported embedding provider: '{config.provider}'")

import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Type

logger = logging.getLogger(__name__)


class BaseVectorDB(ABC):
    """Abstract base class for Vector Database implementations."""

    @abstractmethod
    async def create_collection(
        self,
        collection_name: str,
        vector_size: int,
        distance: str = "Cosine",
        image_vector_size: int | None = None,
    ) -> None:
        """Create a collection/index with specified vector size and distance metric.

        ``image_vector_size`` defaults to ``vector_size`` when not supplied.
        """
        pass

    @abstractmethod
    async def insert(
        self,
        collection_name: str,
        ids: list[str | int],
        vectors: list[list[float]],
        payloads: list[dict[str, Any]] | None = None,
    ) -> None:
        """Insert vectors and metadata payloads into a collection."""
        pass

    @abstractmethod
    async def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 5,
        filter_dict: dict[str, Any] | None = None,
        query_text: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search for vectors similar to the query vector."""
        pass

    @abstractmethod
    async def delete(
        self,
        collection_name: str,
        ids: list[str | int],
    ) -> None:
        """Delete vectors by their IDs."""
        pass


class VectorDBFactory:
    """Registry-based factory for dynamically instantiating Vector Databases."""

    _registry: dict[str, Type[BaseVectorDB]] = {}

    @classmethod
    def register(cls, name: str) -> Callable:
        """Decorator to register a VectorDB implementation class under a given name."""

        def inner_wrapper(wrapped_class: Type[BaseVectorDB]) -> Type[BaseVectorDB]:
            if name in cls._registry:
                logger.warning(f"VectorDB '{name}' is already registered. Overwriting.")
            cls._registry[name] = wrapped_class
            return wrapped_class

        return inner_wrapper

    @classmethod
    def create(cls, name: str, **kwargs: Any) -> BaseVectorDB:
        """Instantiate a VectorDB using its registered name and connection parameters."""
        if name not in cls._registry:
            raise ValueError(f"VectorDB type '{name}' is not registered.")

        db_class = cls._registry[name]
        return db_class(**kwargs)

from unittest.mock import patch

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from src.tools.qdrant_db import QdrantVectorDB
from src.tools.vectordb_base import VectorDBFactory


@pytest.fixture(scope="module")
def otel_setup():
    """Sets up an in-memory span exporter for OpenTelemetry tracing tests."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    processor = SimpleSpanProcessor(exporter)
    provider.add_span_processor(processor)

    yield provider, exporter


@pytest.mark.asyncio
async def test_qdrant_vectordb_crud_and_tracing(otel_setup):
    """Verify CRUD operations on QdrantVectorDB in-memory and ensure OTEL tracing is correctly instrumented."""
    provider, exporter = otel_setup

    # 1. Create client using in-memory location
    db = VectorDBFactory.create("qdrant", location=":memory:")
    assert isinstance(db, QdrantVectorDB)

    # 2. Patch trace provider inside qdrant_db to use our mock otel exporter

    with patch("src.tools.qdrant_db.trace.get_tracer") as mock_get_tracer:
        mock_get_tracer.return_value = provider.get_tracer("qdrant-db")

        # 3. Create Collection
        await db.create_collection("test_col", vector_size=4, distance="Cosine")

        # Check create_collection span
        spans = exporter.get_finished_spans()
        assert len(spans) >= 1
        assert spans[-1].name == "create_collection"
        assert spans[-1].attributes.get("db.name") == "test_col"

        # 4. Insert point
        ids = [1, "8b173167-9c90-482a-9e7f-61011aa3eb75"]
        vectors = [[0.1, 0.2, 0.3, 0.4], [0.5, 0.6, 0.7, 0.8]]
        payloads = [
            {"text": "First document", "tag": "science"},
            {"text": "Second document", "tag": "history"},
        ]

        exporter.clear()
        await db.insert("test_col", ids=ids, vectors=vectors, payloads=payloads)

        # Check insert span
        spans = exporter.get_finished_spans()
        assert len(spans) >= 1
        assert spans[-1].name == "insert"
        assert spans[-1].attributes.get("db.insert.count") == 2  # noqa: PLR2004

        # 5. Search point with filter
        exporter.clear()
        results = await db.search(
            collection_name="test_col",
            query_vector=[0.1, 0.2, 0.3, 0.4],
            limit=1,
            filter_dict={"tag": "science"},
            query_text="Sample search query",
        )

        assert len(results) == 1
        assert results[0]["id"] == 1
        assert results[0]["payload"]["text"] == "First document"

        # Check search retriever span
        spans = exporter.get_finished_spans()
        assert len(spans) >= 1
        search_span = spans[-1]
        assert search_span.name == "search"
        assert search_span.attributes.get("retrieval.documents.0.document.id") == "1"
        assert (
            search_span.attributes.get("retrieval.documents.0.document.content") == "First document"
        )
        assert search_span.attributes.get("db.name") == "test_col"

        # 6. Delete point
        exporter.clear()
        await db.delete("test_col", ids=[1])

        # Check delete span
        spans = exporter.get_finished_spans()
        assert len(spans) >= 1
        assert spans[-1].name == "delete"

        # Check deleted points
        results2 = await db.search(
            collection_name="test_col", query_vector=[0.1, 0.2, 0.3, 0.4], limit=5
        )
        assert len(results2) == 1
        assert results2[0]["id"] == "8b173167-9c90-482a-9e7f-61011aa3eb75"

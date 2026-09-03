import uuid

import pytest

from src.tools.qdrant_db import QdrantVectorDB


@pytest.mark.asyncio
async def test_qdrant_hybrid_and_multimodal_search():
    db = QdrantVectorDB(location=":memory:")
    collection_name = "test_hybrid_collection"

    # 1. Create collection with named/sparse config
    await db.create_collection(
        collection_name=collection_name,
        vector_size=3,
        distance="Cosine",
        image_vector_size=512,
    )

    # 2. Insert points
    namespace = uuid.UUID("37000000-0000-0000-0000-000000000037")
    point1_id = str(uuid.uuid5(namespace, "point-1"))
    point2_id = str(uuid.uuid5(namespace, "point-2"))
    ids: list[str | int] = [point1_id, point2_id]
    vectors = [
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
    ]
    payloads = [
        {
            "text": "First test doc",
            "filepath": "doc1.txt",
            "chunk_index": 0,
            "image": [1.0] + [0.0] * 511,
        },
        {
            "text": "Second doc",
            "filepath": "doc2.txt",
            "chunk_index": 1,
            "image": [0.0] + [1.0] * 511,
        },
    ]
    await db.insert(collection_name, ids, vectors, payloads)

    # 3. Test hybrid search
    hits = await db.search(
        collection_name=collection_name,
        query_vector=[1.0, 0.0, 0.0],
        limit=2,
        search_type="hybrid",
        query_text="First test doc",
    )
    assert len(hits) > 0
    assert hits[0]["id"] == point1_id

    # 4. Test image/multimodal search
    hits_image = await db.search(
        collection_name=collection_name,
        query_vector=[1.0] + [0.0] * 511,
        limit=2,
        search_type="image",
    )
    assert len(hits_image) > 0
    assert hits_image[0]["id"] == point1_id

    # 5. Test answer fields filtering
    hits_filtered = await db.search(
        collection_name=collection_name,
        query_vector=[1.0, 0.0, 0.0],
        limit=2,
        allowed_answer_fields=["filepath"],
    )
    assert "filepath" in hits_filtered[0]["payload"]
    assert "text" not in hits_filtered[0]["payload"]

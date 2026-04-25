import os
from typing import Any

try:
    from pymongo import MongoClient
    from pymongo.errors import PyMongoError
except ModuleNotFoundError:  # pragma: no cover - depends on local environment
    MongoClient = None

    class PyMongoError(Exception):
        pass


MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "imageuploader")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "image_results")
MONGO_VECTOR_DB_NAME = os.getenv("MONGO_VECTOR_DB_NAME", f"{MONGO_DB_NAME}_vectors")
MONGO_VECTOR_COLLECTION = os.getenv("MONGO_VECTOR_COLLECTION", "image_embeddings")
MONGO_VECTOR_INDEX = os.getenv("MONGO_VECTOR_INDEX", "image_embedding_index")

_client: Any = None


def get_client():
    # Keep MongoDB access in one file so the rest of the app does not depend on pymongo details.
    if MongoClient is None:
        raise RuntimeError("pymongo is not installed.")

    global _client
    if _client is None:
        _client = MongoClient(MONGO_URI)
    return _client


def get_document_collection():
    client = get_client()
    database = client[MONGO_DB_NAME]
    return database[MONGO_COLLECTION]


def get_vector_collection():
    client = get_client()
    database = client[MONGO_VECTOR_DB_NAME]
    return database[MONGO_VECTOR_COLLECTION]


def ensure_indexes() -> None:
    document_collection = get_document_collection()
    vector_collection = get_vector_collection()

    document_collection.create_index("event_id", unique=True)
    document_collection.create_index("classification.label")
    vector_collection.create_index("event_id", unique=True)

    try:
        vector_collection.database.command(
            {
                "createSearchIndexes": vector_collection.name,
                "indexes": [
                    {
                        "name": MONGO_VECTOR_INDEX,
                        "definition": {
                            "fields": [
                                {
                                    "type": "vector",
                                    "path": "vector",
                                    "numDimensions": 1536,
                                    "similarity": "cosine",
                                }
                            ]
                        },
                    }
                ],
            }
        )
    except PyMongoError:
        # Vector search setup depends on MongoDB deployment support.
        pass


def save_result(document: dict[str, Any]) -> str:
    # Store metadata and vectors separately so the two Mongo databases can evolve independently.
    document_collection = get_document_collection()
    vector_collection = get_vector_collection()
    ensure_indexes()

    metadata_document = dict(document)
    embedding = dict(metadata_document.pop("embedding", {}) or {})
    vector_document = {
        "event_id": document["event_id"],
        "vector": embedding.get("vector", []),
        "source_text": embedding.get("source_text", ""),
        "provider": embedding.get("provider", "unknown"),
    }
    if "model" in embedding:
        vector_document["model"] = embedding["model"]

    metadata_document["embedding"] = {
        "source_text": vector_document["source_text"],
        "provider": vector_document["provider"],
    }
    if "model" in vector_document:
        metadata_document["embedding"]["model"] = vector_document["model"]

    document_collection.replace_one(
        {"event_id": metadata_document["event_id"]},
        metadata_document,
        upsert=True,
    )
    vector_collection.replace_one(
        {"event_id": vector_document["event_id"]},
        vector_document,
        upsert=True,
    )
    return document["event_id"]


def _merge_embedding(document: dict[str, Any] | None, vector_document: dict[str, Any] | None) -> dict[str, Any] | None:
    if document is None:
        return None

    merged = dict(document)
    embedding = dict(merged.get("embedding", {}) or {})
    if vector_document is not None:
        embedding["vector"] = vector_document.get("vector", [])
        embedding["source_text"] = vector_document.get("source_text", embedding.get("source_text", ""))
        embedding["provider"] = vector_document.get("provider", embedding.get("provider", "unknown"))
        if "model" in vector_document:
            embedding["model"] = vector_document["model"]
    merged["embedding"] = embedding
    return merged


def get_result_by_event_id(event_id: str) -> dict[str, Any] | None:
    try:
        document_collection = get_document_collection()
        vector_collection = get_vector_collection()
    except RuntimeError:
        return None

    document = document_collection.find_one({"event_id": event_id}, {"_id": 0})
    vector_document = vector_collection.find_one({"event_id": event_id}, {"_id": 0})
    return _merge_embedding(document, vector_document)


def find_by_label(label: str) -> list[dict[str, Any]]:
    # This is the simplest future search path before vector search is added.
    try:
        collection = get_document_collection()
    except RuntimeError:
        return []
    cursor = collection.find({"classification.label": label}, {"_id": 0})
    return list(cursor)


def vector_search(query_vector: list[float], limit: int = 5) -> list[dict[str, Any]]:
    if not query_vector:
        return []

    try:
        document_collection = get_document_collection()
        vector_collection = get_vector_collection()
    except RuntimeError:
        return []
    pipeline = [
        {
            "$vectorSearch": {
                "index": MONGO_VECTOR_INDEX,
                "path": "vector",
                "queryVector": query_vector,
                "numCandidates": max(limit * 5, 20),
                "limit": limit,
            }
        },
        {
            "$project": {
                "_id": 0,
                "event_id": 1,
                "vector": 1,
                "source_text": 1,
                "provider": 1,
                "model": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]
    matches = list(vector_collection.aggregate(pipeline))
    if not matches:
        return []

    event_ids = [match["event_id"] for match in matches]
    metadata_documents = {
        document["event_id"]: document
        for document in document_collection.find({"event_id": {"$in": event_ids}}, {"_id": 0})
    }

    results: list[dict[str, Any]] = []
    for match in matches:
        merged = _merge_embedding(
            metadata_documents.get(match["event_id"]),
            {
                "vector": match.get("vector", []),
                "source_text": match.get("source_text", ""),
                "provider": match.get("provider", "unknown"),
                "model": match.get("model"),
            },
        )
        if merged is None:
            continue
        merged["score"] = match["score"]
        results.append(merged)
    return results

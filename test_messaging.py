import json
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

import app
from models import TOPIC, Event, create_event, result_key
from worker import handle_message, processed_event_ids


client = TestClient(app.app)
# here the tests call my FastAPI routes without having to manually run uvicorn

# lets me test API endpoints like /images, /results, and /search/similar directly inside the test file

# Since the worker remembers processed event IDs, I clear that set before each test so each test starts fresh and does not affect the next one.
def setup_function() -> None:
    # Reset duplicate tracking so each test starts with a clean worker state.
    processed_event_ids.clear()


def test_valid_event_schema() -> None:
    # This checks that every event includes the shared fields the API and worker both expect.
    event = create_event(
        TOPIC,
        {
            "batch_id": "batch-1",
            "image_index": 0,
            "image_name": "cat.jpg",
            "image_path": "uploads/cat.jpg",
        },
    )

    assert event.topic == TOPIC
    assert event.event_id
    assert event.timestamp
    assert event.payload.image_name == "cat.jpg"
    assert event.payload.image_path == "uploads/cat.jpg"

# This proves the API publishes one Redis event per uploaded image. Since two images are uploaded, Redis publish should be called twice
def test_publish_called_for_each_uploaded_image() -> None:
    # This simulates a real upload request and confirms the API publishes one Redis event per image.
    with patch.object(app.redis_client, "publish") as publish:
        response = client.post(
            "/images",
            files=[
                ("images", ("cat.jpg", b"cat-bytes", "image/jpeg")),
                ("images", ("dog.png", b"dog-bytes", "image/png")),
            ],
        )

    assert response.status_code == 202
    body = response.json()

    # The API should emit one Redis event for each uploaded image in the batch.
    assert body["count"] == 2
    assert len(body["items"]) == 2
    assert publish.call_count == 2

    first_topic, first_raw_event = publish.call_args_list[0].args
    first_event = Event.model_validate_json(first_raw_event)
    second_topic, second_raw_event = publish.call_args_list[1].args
    second_event = Event.model_validate_json(second_raw_event)

    assert first_topic == TOPIC
    assert second_topic == TOPIC
    assert first_event.payload.image_name == "cat.jpg"
    assert second_event.payload.image_name == "dog.png"
    assert first_event.payload.batch_id == second_event.payload.batch_id


def test_duplicate_event_ignored() -> None:
    # This proves the worker does not process the same event twice, which avoids duplicate writes.
    event = create_event(
        TOPIC,
        {
            "batch_id": "batch-1",
            "image_index": 0,
            "image_name": "cat.jpg",
            "image_path": "uploads/cat.jpg",
        },
    )
    analyzer = Mock(
        return_value={
            "classification": {
                "label": "cat",
                "confidence": "high",
                "reasoning": "Pointed ears and whiskers are visible.",
                "provider": "test",
            },
            "embedding": {
                "vector": [0.1, 0.2, 0.3],
                "source_text": "image=cat.jpg; animal=cat",
                "provider": "test",
            },
        }
    )
    mongo_saver = Mock()

    first = handle_message(event.model_dump_json(), analyzer=analyzer, mongo_saver=mongo_saver)
    second = handle_message(event.model_dump_json(), analyzer=analyzer, mongo_saver=mongo_saver)

    assert first is not None
    assert second is None
    analyzer.assert_called_once()
    mongo_saver.assert_called_once()


def test_malformed_event_handled_safely() -> None:
    # This makes sure bad JSON data is ignored safely instead of crashing the worker loop.
    assert handle_message('{"bad":"data"}') is None


def test_worker_stores_classification_and_embedding() -> None:
    # This checks that the worker saves the AI result payload, including both classification text and embedding data.
    event = create_event(
        TOPIC,
        {
            "batch_id": "batch-1",
            "image_index": 1,
            "image_name": "lizard.jpg",
            "image_path": "uploads/lizard.jpg",
        },
    )
    stored_results: dict[str, str] = {}
    saved_to_mongo: list[dict[str, object]] = []

    class FakeStore:
        def set(self, key: str, value: str) -> None:
            stored_results[key] = value

    result = handle_message(
        event.model_dump_json(),
        analyzer=lambda image_path, image_name: {
            "classification": {
                "label": "lizard",
                "confidence": "high",
                "reasoning": f"{image_name} shows scales and a long tail.",
                "provider": "test",
            },
            "embedding": {
                "vector": [0.4, 0.5, 0.6],
                "source_text": f"image={image_name}; animal=lizard",
                "provider": "test",
            },
        },
        result_store=FakeStore(),
        mongo_saver=lambda document: saved_to_mongo.append(document),
    )

    assert result is not None
    assert result["classification"]["label"] == "lizard"
    assert result["embedding"]["vector"] == [0.4, 0.5, 0.6]
    assert saved_to_mongo[0]["event_id"] == event.event_id

    stored_payload = json.loads(stored_results[result_key(event.event_id)])
    assert stored_payload["image_index"] == 1
    assert stored_payload["classification"]["label"] == "lizard"
    assert stored_payload["embedding"]["source_text"] == "image=lizard.jpg; animal=lizard"


def test_results_endpoint_hides_embedding_vector() -> None:
    # This confirms the API returns the result but removes the raw vector before sending data back to the client.
    event_id = "event-123"
    with patch.object(
        app.redis_client,
        "get",
        return_value=json.dumps(
            {
                "event_id": event_id,
                "classification": {"label": "cat"},
                "embedding": {
                    "vector": [0.1, 0.2, 0.3],
                    "source_text": "image=cat.jpg; animal=cat",
                },
            }
        ),
    ):
        response = client.get(f"/results/{event_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert "vector" not in payload["embedding"]


def test_label_search_hides_embedding_vector() -> None:
    # This verifies label-based search still works while keeping the raw embedding vector private.
    with patch.object(
        app,
        "find_by_label",
        return_value=[
            {
                "event_id": "event-123",
                "classification": {"label": "cat"},
                "embedding": {
                    "vector": [0.1, 0.2, 0.3],
                    "source_text": "image=cat.jpg; animal=cat",
                },
            }
        ],
    ):
        response = client.get("/search/label/cat")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert "vector" not in payload["results"][0]["embedding"]


def test_vector_search_uses_query_embedding_and_hides_embedding_vector() -> None:
    # This checks the vector search flow: embed the text query, search for matches, and hide raw vectors in the response.
    with patch.object(
        app,
        "embed_text",
        return_value={"vector": [0.9, 0.8], "source_text": "cat", "provider": "test"},
    ), patch.object(
        app,
        "vector_search",
        return_value=[
            {
                "event_id": "event-123",
                "classification": {"label": "cat"},
                "embedding": {
                    "vector": [0.1, 0.2, 0.3],
                    "source_text": "image=cat.jpg; animal=cat",
                },
                "score": 0.98,
            }
        ],
    ):
        response = client.post("/search/similar", json={"query": "cat", "limit": 3})

    assert response.status_code == 200
    payload = response.json()
    assert payload["query_type"] == "vector"
    assert payload["count"] == 1
    assert "vector" not in payload["results"][0]["embedding"]

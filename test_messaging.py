from unittest.mock import patch

from fastapi.testclient import TestClient

import app
from models import TOPIC, Event, create_event
from worker import handle_message, processed_event_ids


client = TestClient(app.app)


def setup_function() -> None:
    processed_event_ids.clear()


def test_valid_event_schema() -> None:
    event = create_event(
        TOPIC,
        {"image_name": "photo.jpg", "image_url": "https://example.com/photo.jpg"},
    )

    assert event.topic == TOPIC
    assert event.event_id
    assert event.timestamp
    assert event.payload["image_name"] == "photo.jpg"


def test_publish_called_correctly() -> None:
    with patch.object(app.redis_client, "publish") as publish:
        response = client.post(
            "/images",
            json={
                "image_name": "photo.jpg",
                "image_url": "https://example.com/photo.jpg",
            },
        )

        assert response.status_code == 202
        publish.assert_called_once()
        topic, raw_event = publish.call_args.args
        event = Event.model_validate_json(raw_event)
        assert topic == TOPIC
        assert event.topic == TOPIC
        assert event.payload["image_name"] == "photo.jpg"


def test_duplicate_event_ignored() -> None:
    event = create_event(
        TOPIC,
        {"image_name": "photo.jpg", "image_url": "https://example.com/photo.jpg"},
    )
    raw_event = event.model_dump_json()

    first = handle_message(raw_event)
    second = handle_message(raw_event)

    assert first is not None
    assert second is None


def test_malformed_event_handled_safely() -> None:
    result = handle_message('{"bad":"data"}')

    assert result is None

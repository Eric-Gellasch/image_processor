import redis
from pydantic import ValidationError

from models import Event, TOPIC


processed_event_ids: set[str] = set()


def handle_message(raw_message: str) -> dict | None:
    try:
        event = Event.model_validate_json(raw_message)
    except ValidationError:
        return None

    if event.topic != TOPIC or event.event_id in processed_event_ids:
        return None

    processed_event_ids.add(event.event_id)
    return {
        "status": "processed",
        "event_id": event.event_id,
        "image_name": event.payload.get("image_name"),
        "image_url": event.payload.get("image_url"),
    }


def run_worker() -> None:
    redis_client = redis.Redis(host="localhost", port=6379, decode_responses=True)
    pubsub = redis_client.pubsub()
    pubsub.subscribe(TOPIC)

    for message in pubsub.listen():
        if message.get("type") != "message":
            continue

        result = handle_message(message["data"])
        if result is not None:
            print(result)


if __name__ == "__main__":
    run_worker()

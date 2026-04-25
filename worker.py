import json
from datetime import datetime, timezone

import redis
from pydantic import ValidationError
# makes sure redis messages have expected structure

from classifier import analyze_image
from models import Event, TOPIC, result_key
from mongo_store import save_result
 #imports from models.py the event, redis channel name, redis key
# imports the function that saves to mongodb


processed_event_ids: set[str] = set()
# creates an empty set to remember which events have already been processed
# this helps so that you dont process the same event twice


def redact_vectors(document: dict) -> dict:
    sanitized = json.loads(json.dumps(document))
    embedding = sanitized.get("embedding")
    if isinstance(embedding, dict):
        embedding.pop("vector", None)
    return sanitized
# seperates the long vector under a variable named embedding

#{
   # "embedding": {
  #      "vector": [0.1, 0.2, 0.3],
 #       "provider": "openai"
#    }
# basically removing vector from the document so it is not returned in the API response, 
# this is because the vector can be very long and we dont want to return it in the API response 
# we only want to return the metadata about the embedding
#{
   # "embedding": {
 #       "provider": "openai"
#    }


# THIS IS the main processing function as the subscriber
def handle_message(
    raw_message: str,
    # recieves a string
    analyzer=analyze_image,
    # calls my image analyzer function
    result_store=None,
    mongo_saver=save_result,
) -> dict | None:
    try:
        event = Event.model_validate_json(raw_message)
        # takes raw json from redis and turns to event object, if it doesnt match the expected structure it will 
        # raise a validation error and we will ignore the message
    except ValidationError:
        # Ignore malformed messages instead of crashing the subscriber loop.
        return None

    if event.topic != TOPIC or event.event_id in processed_event_ids:
        return None
    # ignores events if the worker receives a message that is not on the expected topic or if the event id has already been processed
    # this helps ensure that the worker only processes each event once and ignores any messages that are not relevant to it

    processed_event_ids.add(event.event_id)
    try:
        # The worker does all model work after upload so the API response stays quick.
        # The API does not wait for OpenAI/image processing during upload. It just publishes a message and returns quickly.
        analysis = analyzer(event.payload.image_path, event.payload.image_name)
    except Exception as exc:
        analysis = {
            "classification": {
                "label": "unknown",
                "confidence": "low",
                "reasoning": f"Image analysis failed: {exc}",
                "provider": "error",
            },
            "embedding": {
                "vector": [],
                "source_text": "",
                "provider": "error",
            },
        }

    result = {
        "event_id": event.event_id,
        "batch_id": event.payload.batch_id,
        "image_index": event.payload.image_index,
        "image_name": event.payload.image_name,
        "image_path": event.payload.image_path,
        "classification": analysis["classification"],
        "embedding": analysis["embedding"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    if result_store is not None:
        # Save the finished payload so the API can return it from /results/{event_id}.
        result_store.set(result_key(event.event_id), json.dumps(result))

    if mongo_saver is not None:
        try:
            mongo_saver(result)
        except Exception:
            # Redis polling should still work even if MongoDB is unavailable.
            pass

    return result


def run_worker() -> None:
    redis_client = redis.Redis(host="localhost", port=6379, decode_responses=True)
    pubsub = redis_client.pubsub()
    # Listen for new image submission events from the API.
    pubsub.subscribe(TOPIC)

    for message in pubsub.listen():
        if message.get("type") != "message":
            continue

        result = handle_message(message["data"], result_store=redis_client)
        if result is not None:
            print(redact_vectors(result))


if __name__ == "__main__":
    run_worker()

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field
# THIS IS THE SHARED MESSAGE CHANNLE 
# - defines what message channel to use, valid messageages, where to sdave

TOPIC = "image.submitted" # this is the redis channel


class ImagePayload(BaseModel):
    # This is the minimum data the worker needs to find and describe one image.
    batch_id: str
    image_index: int
    image_name: str
    image_path: str


class Event(BaseModel):
    # Every message on Redis uses the same event wrapper. Defines the full message from redis
    topic: str
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    payload: ImagePayload


def create_event(topic: str, payload: dict[str, str | int]) -> Event:
    return Event(topic=topic, payload=payload)
    # helper function that creates event


def result_key(event_id: str) -> str:
    # Keep API reads and worker writes pointed at the same Redis key format.
    return f"image-result:{event_id}"

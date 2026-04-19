from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


TOPIC = "image.submitted"


class Event(BaseModel):
    topic: str
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    payload: dict[str, Any]


def create_event(topic: str, payload: dict[str, Any]) -> Event:
    return Event(topic=topic, payload=payload)

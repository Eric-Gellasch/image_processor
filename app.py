from fastapi import FastAPI
from pydantic import BaseModel
import redis

from models import TOPIC, create_event


class ImageSubmission(BaseModel):
    image_name: str
    image_url: str


app = FastAPI()
redis_client = redis.Redis(host="localhost", port=6379, decode_responses=True)


@app.get("/health")
async def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/images", status_code=202)
async def submit_image(body: ImageSubmission) -> dict[str, str]:
    event = create_event(
        topic=TOPIC,
        payload={"image_name": body.image_name, "image_url": body.image_url},
    )
    redis_client.publish(TOPIC, event.model_dump_json())
    return {"status": "submitted", "event_id": event.event_id}

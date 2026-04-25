import json # will convert json from redis ro python
from pathlib import Path
from uuid import uuid4 # generates unique ids

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
import redis

from classifier import embed_text
from models import TOPIC, create_event, result_key # from the models
from mongo_store import find_by_label, get_result_by_event_id, vector_search
from worker import redact_vectors
# gives you the events, key


app = FastAPI()
# defines the localhost and port for redis
redis_client = redis.Redis(host="localhost", port=6379, decode_responses=True)
# Store uploaded files locally so the worker can process them asynchronously.
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


class SimilarSearchRequest(BaseModel):
    query: str
    limit: int = Field(default=5, ge=1, le=20)


@app.get("/health")
async def health() -> dict[str, bool]:
    return {"ok": True}
# ^ check function ot see if the API is running
# this works when you punch it in the browser

# meat and potatoes this is how your API accepts the images
# remeber post from earlier in the semester
@app.post("/images", status_code=202)
async def submit_images(images: list[UploadFile] = File(...)) -> dict[str, object]:
    # Accept repeated "images" form fields so one request can submit a full batch.
    #  this allows you to dubmit multiple images
    if not images:
        raise HTTPException(status_code=400, detail="At least one image is required.")
# if you submit nothing and execute you will get the bad request
    batch_id = str(uuid4())
# creates a unique id for the image using uuid4 sjbfiuwpbqpiuh-983...
    submitted_items: list[dict[str, str]] = []
# creates a place ot upload a list of whay was uploaded
    for index, upload in enumerate(images):
# loops through uploaded images
        if not upload.filename:
            raise HTTPException(status_code=400, detail="Image file must have a name.")
# checks filename^
        stored_name = f"{uuid4()}{Path(upload.filename).suffix}"
# makes it so the uploaded file is stored with its key
        stored_path = UPLOAD_DIR / stored_name
        # Save the raw bytes now and let the worker inspect the file later.
        stored_path.write_bytes(await upload.read())

        event = create_event(
            topic=TOPIC,
            payload={
                "batch_id": batch_id,
                "image_index": index,
                "image_name": upload.filename,
                "image_path": str(stored_path),
            },
        )
        # Publish one event per image so the worker can process each file independently.
        # very important step for the worker to know when a new image is uploaded and ready for processing

        # below publishes the event to redis for the worker to pick it up
        redis_client.publish(TOPIC, event.model_dump_json())
        submitted_items.append(
            {
                "event_id": event.event_id,
                "image_name": upload.filename,
                "image_path": str(stored_path),
            }
        )
# ^ stores the unique things about the image
    return {
        "status": "submitted",
        "batch_id": batch_id,
        "count": len(images),
        "items": submitted_items,
    }


@app.get("/results/{event_id}")
# this gets your API endpoint
async def get_result(event_id: str) -> dict[str, object]:
    # The worker stores finished results in Redis under a predictable key. in json format 
    result = redis_client.get(result_key(event_id))
    # asks redis if there is a result saved for the given event id
    if result is not None:
        payload = json.loads(result)
        payload["status"] = "completed"
        return redact_vectors(payload)
    # when an event is complete in redis the form needs to be converted back from json, this converts it

    mongo_result = get_result_by_event_id(event_id)
    if mongo_result is None:
        return {"status": "processing", "event_id": event_id}

    payload = redact_vectors(mongo_result)
    payload["status"] = "completed"
    return payload
# checks if mongo IF NOT FOUND IN REDIS got the data and returns processing or completed depending on the status of the data
# IF THE DATA IS NOT FOUND ANYWHERE say it is still processing


@app.get("/search/label/{label}")
# this is your search endpoint for searching by label, it will return all the images with the given label
async def search_by_label(label: str) -> dict[str, object]:
    matches = [redact_vectors(document) for document in find_by_label(label)]
    # this searches mongo for the given label and returns the results, 
    # it also redacts the vectors so they are not returned in the API response
    return {
        "query_type": "label",
        "label": label,
        "count": len(matches),
        "results": matches,
    }


@app.post("/search/similar")
async def search_similar_images(request: SimilarSearchRequest) -> dict[str, object]:
    embedding = embed_text(request.query)
    if not embedding["vector"]:
        raise HTTPException(
            status_code=503,
            detail="Text embeddings are not available until OPENAI_API_KEY is configured.",
        )
        # helps search for similar images in the dbs based on the text query, 
        # if the embedding vector is empty it means the API key is not configured and it will return a 503 error

    matches = [
        redact_vectors(document)
        for document in vector_search(embedding["vector"], request.limit)
    ]
    return {
        "query_type": "vector",
        "query": request.query,
        "count": len(matches),
        "results": matches,
    }
# creates a list of matching documents
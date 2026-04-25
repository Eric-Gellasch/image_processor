ProjectNotes
Need to develop an image uploader that uses asynchronous integration 

reccomends pushing data to an external API that is stored in a server 
rather then pushing it locally, there were 3 options

save in .env file do not publish publicly 

Events
image uploade
image processed
image proc-requests
image annotate
image embedded
image processed
image query

Run some tests using these venets and simulated data 

Requirements:
- Only 4 files: app.py, worker.py, models.py, test_messaging.py
- One Redis topic: image.submitted
- Event schema must include: topic, event_id, timestamp, payload
- API should expose POST /images and publish image.submitted
- Worker should subscribe to image.submitted and simulate processing
- Add pytest tests for:
  1) valid event schema
  2) publish called correctly
  3) duplicate event ignored
  4) malformed event handled safely
- Keep the code as simple and short as possible
- Do not add embeddings, vector DB, or extra abstractions
- Explain each file briefly

How the async flow works
- Client sends a request to the API at POST /images
- app.py receives the request and creates an event
- The event uses this structure: topic, event_id, timestamp, payload
- app.py publishes that event to Redis on image.submitted
- worker.py subscribes to image.submitted
- When Redis receives the published event, the worker is notified
- worker.py simulates processing and ignores duplicates or malformed events safely

Simple diagram
client -> app.py -> Redis topic image.submitted -> worker.py

Important async note
- The API and worker are not doing the same job at the same time
- The API receives the request first
- Then the API publishes the event to Redis
- Then the worker processes it separately
- Async means the API does not wait for the worker to finish before responding

How this fits the event manager idea
- models.py defines the event structure
- app.py creates and publishes events
- worker.py handles subscribed events
- In this small project, those pieces together act like a simple event manager pattern

What each file does
- app.py: FastAPI entry point with POST /images that publishes image.submitted
- worker.py: Redis subscriber that listens for image.submitted and simulates processing
- models.py: shared event schema and event creation helper
- test_messaging.py: pytest tests for schema, publishing, duplicates, and malformed events

What to run
- Run the API server from app.py
- Run the worker from worker.py

Commands
- API server: uvicorn app:app --reload
- Worker: python worker.py
- Tests: python -m pytest test_messaging.py

Run order
1. Start Redis
2. Start the API server
3. Start the worker
4. Send a POST request to /images

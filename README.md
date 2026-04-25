# Event-Driven Image Uploader

A Python prototype for an asynchronous image uploader using Redis pub/sub, FastAPI, MongoDB, and OpenAI. This is a minimal event-driven system where an API accepts image uploads, publishes events to Redis, a worker processes them asynchronously with AI classification, and results are stored in MongoDB for retrieval and semantic search.

## Project Goal

Build a scalable asynchronous image upload pipeline that:

- accepts image uploads through a REST API
- publishes an event to Redis for each image
- uses a background worker to process images with OpenAI vision classification
- stores results and embeddings in MongoDB
- supports both label-based and semantic similarity search
- validates behavior with unit tests

## Architecture

The system is split into three main components:

1. **API (`app.py`)** — FastAPI server that accepts image uploads and serves search/results queries
2. **Worker (`worker.py`)** — Background processor that subscribes to Redis, analyzes images, and stores results
3. **Storage & AI** — MongoDB for persistent storage, OpenAI for vision classification and embeddings

### Data Flow

```
User uploads images
        ↓
    API endpoint (/images)
        ↓
    Save to disk
        ↓
    Publish event to Redis
        ↓
    API returns 202 (async)
        ↓
    Worker subscribes to Redis
        ↓
    Analyze image with OpenAI Vision
        ↓
    Generate embedding with OpenAI
        ↓
    Store in Redis (fast) + MongoDB (persistent)
        ↓
    Client polls GET /results/{event_id} or searches
```

## Current Features

### API Endpoints

- `GET /health` — Health check
- `POST /images` — Upload one or more images (returns 202 Accepted with event IDs)
- `GET /results/{event_id}` — Retrieve classification result for a single image
- `GET /search/label/{label}` — Find all images with a specific classification label
- `POST /search/similar` — Semantic similarity search using text query

### Messaging

- Redis pub/sub on topic `image.submitted`
- Shared event schema with `event_id`, `topic`, `timestamp`, and `payload`
- Duplicate detection to prevent reprocessing

### Storage

- **Redis** — Fast temporary result storage using predictable key format
- **MongoDB** — Persistent storage split into two collections:
  - Metadata collection for classification and event info
  - Vector collection for embeddings (with vector search index)

### AI Integration

- OpenAI Vision API for animal classification
- OpenAI Embeddings API for semantic search
- Fallback behavior when API key is not configured

### Testing

- Unit tests in `test_messaging.py` for API and worker logic
- Mocked external dependencies (Redis, MongoDB, OpenAI)
- Schema validation and duplicate event detection tests

## File Structure

```
imageuploader/
├── app.py                 # FastAPI application with upload & search endpoints
├── worker.py              # Background worker that processes images
├── models.py              # Shared event schema and utilities
├── classifier.py          # OpenAI vision analysis and embeddings
├── mongo_store.py         # MongoDB connection and queries
├── test_messaging.py      # Unit tests for API and worker
├── testmongo.py           # MongoDB connection verification
├── ProjectNotes.md        # Development notes
├── CodeStructNotes.txt    # Architecture documentation
├── uploads/               # Temporary storage for uploaded images
└── animals/               # Example images for testing
```

## Setup

### 1. Install Dependencies

```bash
pip install fastapi uvicorn redis pymongo openai pydantic
```

Or with a requirements file (if available):
```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Create a `.env` file or set environment variables:

```bash
# OpenAI (required for image classification)
export OPENAI_API_KEY="your-openai-key"
export OPENAI_VISION_MODEL="gpt-4-vision-preview"
export OPENAI_EMBEDDING_MODEL="text-embedding-3-small"

# Redis (defaults to localhost:6379)
export REDIS_HOST="localhost"
export REDIS_PORT="6379"

# MongoDB (defaults to localhost:27017)
export MONGO_URI="mongodb://localhost:27017"
export MONGO_DB_NAME="imageuploader"
export MONGO_COLLECTION="image_results"
export MONGO_VECTOR_DB_NAME="imageuploader_vectors"
export MONGO_VECTOR_COLLECTION="image_embeddings"
```

**Important**: Never commit real credentials to version control. The `.gitignore` file excludes `.env` and sensitive files.

### 3. Start Redis

```bash
redis-server
```

### 4. Start MongoDB

```bash
mongod
```

Or use MongoDB Atlas (cloud) by setting `MONGO_URI` to your connection string.

## Running the Application

### Start the API

```bash
uvicorn app:app --reload
```

The API will be available at `http://localhost:8000`.

### Start the Worker

In a separate terminal:

```bash
python worker.py
```

The worker will subscribe to Redis and process images in the background.

### Run Unit Tests

```bash
pytest test_messaging.py
```

## Usage Example

### 1. Upload Images

```bash
curl -X POST "http://localhost:8000/images" \
  -F "images=@/path/to/cat.jpg" \
  -F "images=@/path/to/dog.png"
```

Response:
```json
{
  "status": "submitted",
  "batch_id": "abc-123",
  "count": 2,
  "items": [
    {
      "event_id": "evt-001",
      "image_name": "cat.jpg",
      "image_path": "uploads/uuid.jpg"
    },
    {
      "event_id": "evt-002",
      "image_name": "dog.png",
      "image_path": "uploads/uuid.png"
    }
  ]
}
```

### 2. Poll for Results

```bash
curl "http://localhost:8000/results/evt-001"
```

Response (while processing):
```json
{
  "status": "processing",
  "event_id": "evt-001"
}
```

Response (after processing):
```json
{
  "status": "completed",
  "event_id": "evt-001",
  "image_name": "cat.jpg",
  "classification": {
    "label": "cat",
    "confidence": "high",
    "reasoning": "Pointed ears and whiskers visible"
  },
  "embedding": {
    "source_text": "image=cat.jpg; animal=cat; ...",
    "provider": "openai"
  }
}
```

### 3. Search by Label

```bash
curl "http://localhost:8000/search/label/cat"
```

### 4. Semantic Search

```bash
curl -X POST "http://localhost:8000/search/similar" \
  -H "Content-Type: application/json" \
  -d '{"query": "a fluffy feline", "limit": 5}'
```

## Key Components

### `app.py` — API Server
- Accepts multipart image uploads
- Publishes events to Redis for async processing
- Serves results from Redis (fast) or MongoDB (persistent)
- Implements search endpoints

### `worker.py` — Background Worker
- Subscribes to Redis pub/sub
- Validates event schema
- Tracks processed event IDs to avoid duplicates
- Calls OpenAI Vision for classification
- Stores results in Redis and MongoDB

### `classifier.py` — AI Integration
- `analyze_image()` — Sends image to OpenAI Vision API with classification prompt
- `embed_text()` — Generates embeddings for semantic search
- Handles API key configuration gracefully

### `mongo_store.py` — Database Layer
- `save_result()` — Stores metadata and vectors separately
- `get_result_by_event_id()` — Merges metadata with vectors
- `find_by_label()` — Label-based search
- `vector_search()` — Semantic similarity search using MongoDB vector search

### `models.py` — Event Schema
- Defines shared `Event` and `ImagePayload` classes
- Ensures API and worker use the same message format
- Provides utilities like `create_event()` and `result_key()`

## Testing

Unit tests use mocks to isolate components:

- **Schema validation**: Ensures events have required fields
- **Publishing**: Verifies one Redis event per uploaded image
- **Duplicate detection**: Confirms worker skips reprocessed events
- **Integration**: Simulates full upload-to-result workflow without real services

Run tests with:
```bash
pytest test_messaging.py -v
```

## Development Notes

- **Async processing**: API returns immediately (202 Accepted) while worker processes in background
- **Error resilience**: Worker continues even if OpenAI or MongoDB is unavailable
- **No secrets in code**: All credentials use environment variables
- **Scalable architecture**: Redis and MongoDB can be replaced with alternatives (e.g., different message brokers or databases)

## Future Enhancements

- Batch processing optimizations
- WebSocket support for real-time result updates
- Caching strategies for popular search queries
- Rate limiting and authentication
- Advanced filtering and pagination for search results
- Image preprocessing and quality validation
- Multi-model support for classification

## License

MIT (or your preferred license)

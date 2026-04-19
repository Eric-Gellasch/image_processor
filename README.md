# Event-Driven Image Uploader

This project is a small Python prototype for an asynchronous image uploader using Redis pub/sub and FastAPI. It is designed as a simple event-driven system where an API publishes image events and a worker subscribes to them and simulates processing.

The goal of this version is to focus on messaging, event structure, and unit testing. Embeddings, vector search, and full annotation storage are intentionally left for a later phase.

## Project Goal

Build a minimal asynchronous image upload pipeline that:

- accepts image-related input through an API
- creates and publishes an event to Redis
- uses a worker to subscribe and simulate processing
- validates the messaging behavior with unit tests

## Current Scope

This version only includes:

- one Redis topic: `image.submitted`
- one API endpoint: `POST /images`
- one worker subscriber
- one shared event schema
- unit tests for messaging behavior

This version does **not** include:

- embeddings
- vector database integration
- image similarity search
- extra abstractions or large architecture layers

## File Structure

```text
app.py
worker.py
models.py
test_messaging.py

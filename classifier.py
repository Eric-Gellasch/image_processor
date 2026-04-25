import base64
import json
import os
from pathlib import Path
from typing import Any

from openai import OpenAI


VISION_MODEL = os.getenv("OPENAI_VISION_MODEL", "gpt-4.1-mini")
EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")


def _guess_mime_type(image_path: Path) -> str:
    # The vision request uses a data URL, so the MIME type must match the file.
    suffix = image_path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".webp":
        return "image/webp"
    if suffix == ".gif":
        return "image/gif"
    return "application/octet-stream"


def _parse_classification(output_text: str) -> dict[str, str]:
    # Fall back to a safe shape if the model does not return valid JSON.
    try:
        parsed = json.loads(output_text)
    except json.JSONDecodeError:
        parsed = {
            "label": "unknown",
            "confidence": "low",
            "reasoning": output_text.strip() or "The model returned an empty response.",
        }

    return {
        "label": parsed.get("label", "unknown"),
        "confidence": parsed.get("confidence", "unknown"),
        "reasoning": parsed.get("reasoning", "No explanation returned."),
    }


def _build_embedding_text(image_name: str, classification: dict[str, str]) -> str:
    # Keep the embedded text small and consistent so later similarity search stays simple.
    return (
        f"image={image_name}; "
        f"animal={classification['label']}; "
        f"confidence={classification['confidence']}; "
        f"reasoning={classification['reasoning']}"
    )


def embed_text(text: str) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {
            "vector": [],
            "source_text": text,
            "provider": "unconfigured",
            "model": EMBEDDING_MODEL,
        }

    client = OpenAI(api_key=api_key)
    embedding_response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
    )
    return {
        "vector": embedding_response.data[0].embedding,
        "source_text": text,
        "provider": "openai",
        "model": EMBEDDING_MODEL,
    }


def analyze_image(image_path: str, image_name: str) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        # Keep the app usable in local development even before API credentials are set.
        classification = {
            "label": "unclassified",
            "confidence": "unknown",
            "reasoning": "OPENAI_API_KEY is not configured for vision classification yet.",
            "provider": "unconfigured",
        }
        return {
            "classification": classification,
            "embedding": {
                "vector": [],
                "source_text": _build_embedding_text(image_name, classification),
                "provider": "unconfigured",
            },
        }

    path = Path(image_path)
    # Read the saved image once and send it to the vision model as a base64 data URL.
    encoded_image = base64.b64encode(path.read_bytes()).decode("utf-8")
    mime_type = _guess_mime_type(path)

    client = OpenAI(api_key=api_key)
    classification_response = client.responses.create(
        model=VISION_MODEL,
        input=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "You classify animals from images. "
                            "Return strict JSON with keys: label, confidence, reasoning."
                        ),
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Identify the main animal in this image as specifically as possible. "
                            "Examples include cat, dog, lizard, snake, bird, horse, or lion. "
                            "If there is no clear animal, use 'unknown'. Return only valid JSON. Do not use markdown. Do not wrap the JSON in ```json."
                        ),
                    },
                    {
                        "type": "input_image",
                        "image_url": f"data:{mime_type};base64,{encoded_image}",
                    },
                ],
            },
        ],
    )

    classification = _parse_classification(classification_response.output_text)
    classification["provider"] = "openai"
    classification["model"] = VISION_MODEL

    # Embed a short text summary of the result so the app has a searchable vector.
    embedding_text = _build_embedding_text(image_name, classification)
    return {
        "classification": classification,
        "embedding": embed_text(embedding_text),
    }

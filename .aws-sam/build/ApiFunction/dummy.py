"""Minimal Gemini API-key smoke test."""

import os
from pathlib import Path

import httpx


def get_api_key() -> str:
    if key := os.getenv("GEMINI_API_KEY"):
        return key

    env_file = Path(__file__).resolve().parent.parent / ".env.local"
    for line in env_file.read_text().splitlines():
        name, separator, value = line.partition("=")
        if separator and name.strip() == "GEMINI_API_KEY":
            return value.strip().strip("\"'")

    raise RuntimeError("GEMINI_API_KEY was not found")


def main() -> None:
    response = httpx.get(
        "https://generativelanguage.googleapis.com/v1beta/models",
        headers={"x-goog-api-key": get_api_key()},
        timeout=30,
    )
    response.raise_for_status()
    model_count = len(response.json().get("models", []))
    print(f"Gemini API key works. Available models: {model_count}")


if __name__ == "__main__":
    main()

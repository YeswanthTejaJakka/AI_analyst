import json
from typing import Any, Optional
import httpx
from app.services.ai.base import LLMProvider


class GeminiProvider(LLMProvider):
    """Google Gemini LLM Provider via standard REST API."""

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        self.api_key = api_key
        self.model = model
        self.base_url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"

    def get_provider_name(self) -> str:
        return f"Gemini ({self.model})"

    async def generate_completion(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_schema: Optional[dict[str, Any]] = None,
        temperature: float = 0.1,
    ) -> str:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not configured.")

        url = f"{self.base_url}?key={self.api_key}"

        contents = []
        if prompt:
            contents.append({"role": "user", "parts": [{"text": prompt}]})

        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
            },
        }

        if system_prompt:
            body["systemInstruction"] = {
                "parts": [{"text": system_prompt}]
            }

        if json_schema:
            body["generationConfig"]["responseMimeType"] = "application/json"
            body["generationConfig"]["responseSchema"] = json_schema

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=body)
            if resp.status_code != 200:
                raise RuntimeError(f"Gemini API returned error {resp.status_code}: {resp.text}")

            data = resp.json()
            try:
                candidate = data["candidates"][0]
                text = candidate["content"]["parts"][0]["text"]
                return text
            except (KeyError, IndexError) as e:
                raise RuntimeError(f"Malformed Gemini response: {data}") from e

import json
from typing import Any, Optional
import httpx
from app.services.ai.base import LLMProvider


class OpenAIProvider(LLMProvider):
    """OpenAI and OpenAI-compatible (Groq, Ollama, DeepSeek) LLM Provider."""

    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1", model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    def get_provider_name(self) -> str:
        return f"OpenAI-Compatible ({self.model})"

    async def generate_completion(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_schema: Optional[dict[str, Any]] = None,
        temperature: float = 0.1,
    ) -> str:
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is not configured.")

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }

        if json_schema:
            body["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=body)
            if resp.status_code != 200:
                raise RuntimeError(f"OpenAI API returned error {resp.status_code}: {resp.text}")

            data = resp.json()
            try:
                return data["choices"][0]["message"]["content"]
            except (KeyError, IndexError) as e:
                raise RuntimeError(f"Malformed OpenAI response: {data}") from e

from app.core.config import settings
from app.services.ai.base import LLMProvider
from app.services.ai.gemini import GeminiProvider
from app.services.ai.heuristic import HeuristicAIProvider
from app.services.ai.openai_provider import OpenAIProvider


def get_llm_provider(provider_type: str = "auto") -> LLMProvider:
    """Factory to retrieve configured LLM provider with graceful fallback."""
    mode = provider_type.lower() if provider_type != "auto" else settings.LLM_PROVIDER.lower()

    if mode in ["gemini", "google"] or (mode == "auto" and settings.GEMINI_API_KEY):
        return GeminiProvider(api_key=settings.GEMINI_API_KEY, model=settings.GEMINI_MODEL)

    if mode in ["openai", "groq", "ollama"] or (mode == "auto" and settings.OPENAI_API_KEY):
        return OpenAIProvider(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
            model=settings.OPENAI_MODEL,
        )

    # Default to deterministic heuristic provider (zero-dependency, always works offline)
    return HeuristicAIProvider()

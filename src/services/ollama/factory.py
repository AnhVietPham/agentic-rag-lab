from src.config import Settings
from src.services.llm.client import LLMClient
from src.services.llm.factory import make_llm_client


def make_ollama_client(settings: Settings | None = None) -> LLMClient:
    """Build the unified LLM client (OpenRouter)."""
    return make_llm_client(settings)

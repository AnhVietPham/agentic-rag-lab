from src.config import Settings, get_settings
from src.services.llm.client import LLMClient


def make_llm_client(settings: Settings | None = None) -> LLMClient:
    resolved = settings if settings is not None else get_settings()
    return LLMClient(resolved)

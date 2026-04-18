"""Backward-compatible import path. Prefer `from src.services.llm import LLMClient`."""

from src.services.llm.client import LLMClient, OllamaClient

__all__ = ["LLMClient", "OllamaClient"]

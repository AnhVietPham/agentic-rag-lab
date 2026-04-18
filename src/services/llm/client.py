import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx
from langchain_core.language_models.chat_models import BaseChatModel

from src.config import Settings
from src.exceptions import OllamaException
from src.services.llm.providers.openrouter_provider import (
    OpenRouterLLMProvider,
    build_rag_payload_sources,
)
from src.services.ollama.prompts import RAGPromptBuilder, ResponseParser

logger = logging.getLogger(__name__)

_DEFAULT_OR_MODEL = "openai/gpt-4o-mini"


class LLMClient:
    """Unified LLM entrypoint via OpenRouter (OpenAI-compatible Chat Completions)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.timeout = httpx.Timeout(float(settings.llm_http_timeout_seconds))
        key = str(getattr(settings, "openrouter_api_key", "") or "").strip()
        self._openrouter: Optional[OpenRouterLLMProvider] = None
        if key:
            self._openrouter = OpenRouterLLMProvider(
                api_key=key,
                base_url=str(settings.openrouter_base_url or "").strip()
                or "https://openrouter.ai/api/v1",
                timeout=self.timeout,
                http_referer=str(getattr(settings, "openrouter_http_referer", "") or ""),
                app_title=str(getattr(settings, "openrouter_app_title", "") or ""),
            )
        self.prompt_builder = RAGPromptBuilder()
        self.response_parser = ResponseParser()

    @property
    def base_url(self) -> str:
        """OpenRouter API base URL (for diagnostics)."""
        return str(self._settings.openrouter_base_url or "").rstrip("/") or "https://openrouter.ai/api/v1"

    @staticmethod
    def uses_openrouter(settings: Settings) -> bool:
        return bool(str(getattr(settings, "openrouter_api_key", "") or "").strip())

    @staticmethod
    def configured(settings: Settings) -> bool:
        return LLMClient.uses_openrouter(settings)

    @property
    def provider_name(self) -> str:
        return "openrouter" if self._openrouter else "none"

    @property
    def default_chat_model(self) -> str:
        m = str(getattr(self._settings, "openrouter_model", "") or "").strip()
        return m or _DEFAULT_OR_MODEL

    @property
    def translation_chat_model(self) -> str:
        """OpenRouter model slug for translation (or same as main if unset)."""
        t = str(getattr(self._settings, "openrouter_translation_model", "") or "").strip()
        return t or self.default_chat_model

    def get_langchain_translation_model(
        self, temperature: float = 0.0
    ) -> BaseChatModel:
        """LangChain chat model using `translation_chat_model` (separate OpenRouter slug)."""
        return self.get_langchain_model(model=self.translation_chat_model, temperature=temperature)

    @staticmethod
    def effective_rag_model(settings: Settings, request_model: str) -> str:
        rm = (request_model or "").strip()
        if rm:
            return rm
        m = str(getattr(settings, "openrouter_model", "") or "").strip()
        return m or _DEFAULT_OR_MODEL

    def get_langchain_model(
        self,
        model: Optional[str] = None,
        temperature: float = 0.0,
    ) -> BaseChatModel:
        """LangChain chat model for agent nodes (guardrail, grading, etc.)."""
        if not self._openrouter:
            raise OllamaException(
                "OPENROUTER_API_KEY is not set. Add it to .env and restart the API."
            )
        m = model or self.default_chat_model
        from langchain_openai import ChatOpenAI

        base = str(self._settings.openrouter_base_url or "").strip().rstrip("/")
        if not base:
            base = "https://openrouter.ai/api/v1"
        referer = str(getattr(self._settings, "openrouter_http_referer", "") or "").strip()
        title = str(getattr(self._settings, "openrouter_app_title", "") or "").strip()
        headers: Dict[str, str] = {}
        if referer:
            headers["HTTP-Referer"] = referer
        if title:
            headers["X-Title"] = title
        return ChatOpenAI(
            model=m,
            api_key=self._settings.openrouter_api_key,
            base_url=base,
            temperature=temperature,
            timeout=float(self._settings.llm_http_timeout_seconds),
            default_headers=headers or None,
        )

    async def health_check(self) -> Dict[str, Any]:
        if not self._openrouter:
            return {
                "status": "unhealthy",
                "message": (
                    "OPENROUTER_API_KEY is not set. LLM features are disabled until you add "
                    "OPENROUTER_API_KEY to .env and restart."
                ),
                "version": "n/a",
                "provider": "none",
            }
        result = await self._openrouter.health_check()
        result["provider"] = "openrouter"
        tm = self.translation_chat_model
        main = self.default_chat_model
        suffix = f"model={main}" if tm == main else f"model={main}, translation_model={tm}"
        result["message"] = f"{result.get('message', 'OpenRouter OK')} — {suffix}"
        return result

    async def list_models(self) -> List[Dict[str, Any]]:
        if not self._openrouter:
            return []
        out = await self._openrouter.list_models_catalog()
        if out:
            return out
        name = self.default_chat_model
        return [{"name": name, "model": name, "provider": "openrouter"}]

    async def generate(
        self, model: str, prompt: str, stream: bool = False, **kwargs: Any
    ) -> Optional[Dict[str, Any]]:
        if not self._openrouter:
            raise OllamaException("OPENROUTER_API_KEY is not set.")
        if stream:
            raise OllamaException("Use generate_stream for stream=True with OpenRouter.")
        text = await self._openrouter.chat_complete(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=float(kwargs.get("temperature", 0.7)),
            max_tokens=int(kwargs.get("max_tokens", 8192)),
        )
        return {"response": text, "model": model}

    async def generate_stream(
        self, model: str, prompt: str, **kwargs: Any
    ) -> AsyncIterator[Dict[str, Any]]:
        if not self._openrouter:
            raise OllamaException("OPENROUTER_API_KEY is not set.")
        async for chunk in self._openrouter.chat_complete_stream(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=float(kwargs.get("temperature", 0.7)),
            max_tokens=int(kwargs.get("max_tokens", 8192)),
        ):
            yield chunk

    async def generate_rag_answer(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        model: str = "llama3.2",
        use_structured_output: bool = False,
    ) -> Dict[str, Any]:
        try:
            if not self._openrouter:
                raise OllamaException(
                    "OPENROUTER_API_KEY is not set. Add it to .env and restart the API."
                )

            logger.info("RAG using OpenRouter model=%s", model)

            if use_structured_output:
                prompt_data = self.prompt_builder.create_structured_prompt(query=query, chunks=chunks)
                schema = prompt_data["format"]
                messages = [
                    {
                        "role": "user",
                        "content": (
                            f"{prompt_data['prompt']}\n\n"
                            "Reply with a single JSON object only, no markdown fences, "
                            "matching this JSON Schema:\n"
                            f"{json.dumps(schema)}"
                        ),
                    }
                ]
                answer_text = await self._openrouter.chat_complete(
                    model=model,
                    messages=messages,
                    temperature=0.7,
                    response_format={"type": "json_object"},
                )
                parsed_response = self.response_parser.parse_structured_response(answer_text)
                return parsed_response

            system, user_content = self.prompt_builder.rag_system_and_user(query, chunks)
            answer_text = await self._openrouter.rag_complete(
                model=model,
                system=system,
                user_content=user_content,
            )
            sources, _ = build_rag_payload_sources(chunks)
            citations = list({c.get("arxiv_id") for c in chunks if c.get("arxiv_id")})
            return {
                "answer": answer_text,
                "sources": sources,
                "confidence": "medium",
                "citations": citations[:5],
            }
        except OllamaException:
            raise
        except Exception as e:
            logger.error("Error generating RAG answer: %s", e)
            raise OllamaException(f"Failed to generate RAG answer: {e}") from e

    async def generate_rag_answer_stream(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        model: str = "llama3.2",
    ):
        try:
            if not self._openrouter:
                raise OllamaException(
                    "OPENROUTER_API_KEY is not set. Add it to .env and restart the API."
                )
            system, user_content = self.prompt_builder.rag_system_and_user(query, chunks)
            async for item in self._openrouter.rag_complete_stream(
                model=model,
                system=system,
                user_content=user_content,
            ):
                yield item
        except OllamaException:
            raise
        except Exception as e:
            logger.error("Error generating streaming RAG answer: %s", e)
            raise OllamaException(f"Failed to generate streaming RAG answer: {e}") from e


# Backward-compatible alias used across the codebase
OllamaClient = LLMClient

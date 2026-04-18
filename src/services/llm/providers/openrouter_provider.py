import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from src.exceptions import OllamaException

logger = logging.getLogger(__name__)


def build_rag_payload_sources(
    chunks: List[Dict[str, Any]],
) -> tuple[List[str], set[str]]:
    sources: List[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        arxiv_id = chunk.get("arxiv_id")
        if arxiv_id:
            arxiv_id_clean = arxiv_id.split("v")[0] if "v" in arxiv_id else arxiv_id
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id_clean}.pdf"
            if pdf_url not in seen:
                sources.append(pdf_url)
                seen.add(pdf_url)
    return sources, seen


class OpenRouterLLMProvider:
    """OpenAI-compatible Chat Completions API (OpenRouter)."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        timeout: httpx.Timeout,
        *,
        http_referer: str = "",
        app_title: str = "",
    ) -> None:
        self._api_key = api_key.strip()
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._http_referer = (http_referer or "").strip()
        self._app_title = (app_title or "").strip()

    def _headers(self) -> Dict[str, str]:
        h: Dict[str, str] = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        if self._http_referer:
            h["HTTP-Referer"] = self._http_referer
        if self._app_title:
            h["X-Title"] = self._app_title
        return h

    async def health_check(self) -> Dict[str, Any]:
        """Lightweight check: authenticated request to OpenRouter."""
        url = f"{self._base}/models"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.get(url, headers=self._headers(), params={"limit": 1})
                if r.status_code == 200:
                    return {
                        "status": "healthy",
                        "message": "OpenRouter API reachable",
                        "version": "cloud",
                    }
                body = (r.text or "")[:300]
                raise OllamaException(
                    f"OpenRouter health check failed: HTTP {r.status_code} — {body}"
                )
        except httpx.HTTPError as e:
            raise OllamaException(f"OpenRouter health check failed: {e}") from e

    async def chat_complete(
        self,
        *,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 8192,
        temperature: float = 0.7,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if response_format is not None:
            payload["response_format"] = response_format
        url = f"{self._base}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.post(url, headers=self._headers(), json=payload)
                if r.status_code != 200:
                    body = (r.text or "")[:800]
                    raise OllamaException(
                        f"OpenRouter chat failed: HTTP {r.status_code} — {body}"
                    )
                data = r.json()
        except OllamaException:
            raise
        except Exception as e:
            raise OllamaException(f"OpenRouter chat failed: {e}") from e

        text = self._message_content_from_response(data)
        if not text.strip():
            raise OllamaException("No response generated from OpenRouter")
        return text

    async def chat_complete_stream(
        self,
        *,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 8192,
        temperature: float = 0.7,
    ) -> AsyncIterator[Dict[str, Any]]:
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        url = f"{self._base}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream(
                    "POST",
                    url,
                    headers=self._headers(),
                    json=payload,
                ) as response:
                    if response.status_code != 200:
                        body = (await response.aread())[:800].decode(errors="replace")
                        raise OllamaException(
                            f"OpenRouter stream failed: HTTP {response.status_code} — {body}"
                        )
                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if raw == "[DONE]":
                            yield {"response": "", "done": True}
                            return
                        try:
                            evt = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        piece = self._delta_content_from_chunk(evt)
                        if piece:
                            yield {"response": piece, "done": False}
            yield {"response": "", "done": True}
        except OllamaException:
            raise
        except Exception as e:
            raise OllamaException(f"OpenRouter streaming failed: {e}") from e

    async def rag_complete(
        self,
        *,
        model: str,
        system: str,
        user_content: str,
        max_tokens: int = 8192,
        temperature: float = 0.7,
    ) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ]
        return await self.chat_complete(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    async def rag_complete_stream(
        self,
        *,
        model: str,
        system: str,
        user_content: str,
        max_tokens: int = 8192,
        temperature: float = 0.7,
    ) -> AsyncIterator[Dict[str, Any]]:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ]
        async for item in self.chat_complete_stream(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        ):
            yield item

    @staticmethod
    def _message_content_from_response(data: Dict[str, Any]) -> str:
        choices = data.get("choices") or []
        if not choices:
            return ""
        msg = (choices[0] or {}).get("message") or {}
        return str(msg.get("content") or "")

    @staticmethod
    def _delta_content_from_chunk(evt: Dict[str, Any]) -> str:
        choices = evt.get("choices") or []
        if not choices:
            return ""
        delta = (choices[0] or {}).get("delta") or {}
        return str(delta.get("content") or "")

    async def list_models_catalog(self, limit: int = 50) -> List[Dict[str, Any]]:
        url = f"{self._base}/models"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.get(url, headers=self._headers())
                if r.status_code != 200:
                    return []
                data = r.json()
                out: List[Dict[str, Any]] = []
                for item in (data.get("data") or [])[:limit]:
                    mid = item.get("id") or item.get("name") or ""
                    if mid:
                        out.append({"name": mid, "model": mid, "provider": "openrouter"})
                return out
        except Exception:
            return []

import asyncio
import logging
from typing import List

import httpx
from src.schemas.embeddings.jina import JinaEmbeddingRequest, JinaEmbeddingResponse

logger = logging.getLogger(__name__)

_MAX_RETRIES = 5
_RETRY_BASE_DELAY = 2.0  # seconds — doubles each attempt: 2, 4, 8, 16, 32


class JinaEmbeddingsClient:
    def __init__(self, api_key: str, base_url: str = "https://api.jina.ai/v1"):
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self.client = httpx.AsyncClient(timeout=30.0)
        logger.info("Jina embeddings client initialized")

    async def _post_with_retry(self, url: str, payload: dict) -> httpx.Response:
        """POST with exponential backoff retry on 429 Too Many Requests."""
        for attempt in range(_MAX_RETRIES):
            response = await self.client.post(url, headers=self.headers, json=payload)
            if response.status_code == 429:
                wait = _RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    f"Rate limited by Jina API (attempt {attempt + 1}/{_MAX_RETRIES}). "
                    f"Retrying in {wait:.0f}s..."
                )
                await asyncio.sleep(wait)
                continue
            response.raise_for_status()
            return response
        response.raise_for_status()
        return response

    async def embed_passages(self, texts: List[str], batch_size: int = 50) -> List[List[float]]:
        embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i: i + batch_size]

            request_data = JinaEmbeddingRequest(
                model="jina-embeddings-v3",
                task="retrieval.passage",
                dimensions=1024,
                input=batch,
            )

            try:
                response = await self._post_with_retry(
                    f"{self.base_url}/embeddings",
                    request_data.model_dump(),
                )
                result = JinaEmbeddingResponse(**response.json())
                batch_embeddings = [item["embedding"] for item in result.data]
                embeddings.extend(batch_embeddings)
                logger.debug(f"Embedded batch of {len(batch)} passages")
            except httpx.HTTPError as e:
                logger.error(f"Error embedding passages: {e}")
                raise

        logger.info(f"Successfully embedded {len(texts)} passages")
        return embeddings

    async def embed_query(self, query: str) -> List[float]:
        request_data = JinaEmbeddingRequest(
            model="jina-embeddings-v3",
            task="retrieval.query",
            dimensions=1024,
            input=[query],
        )

        try:
            response = await self._post_with_retry(
                f"{self.base_url}/embeddings",
                request_data.model_dump(),
            )
            result = JinaEmbeddingResponse(**response.json())
            embedding = result.data[0]["embedding"]
            logger.debug(f"Embedded query: '{query[:50]}...")
            return embedding
        except httpx.HTTPError as e:
            logger.error(f"Error embedding query: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in embed_query: {e}")
            raise
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
        
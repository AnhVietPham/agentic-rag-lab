import logging
from typing import Any, List

from langchain_core.tools import tool

from src.services.embeddings.jina_client import JinaEmbeddingsClient
from src.services.opensearch.client import OpenSearchClient

logger = logging.getLogger(__name__)


def create_retriever_tool(
    opensearch_client: OpenSearchClient,
    embeddings_client: JinaEmbeddingsClient,
    use_hybrid: bool = True,
    top_k: int = 3,
):
    @tool
    async def retrieve_papers(query: str) -> List[dict[str, Any]]:
        """Search and return relevant arXiv research papers.

        Use this tool when the user asks about:
        - Machine learning concepts or techniques
        - Deep learning architectures
        - Natural language processing
        - Computer vision methods
        - AI research topics
        - Specific algorithms or models

        :param query: The search query describing what papers to find
        :returns: JSON-serializable list of {page_content, metadata} for LangGraph ToolMessage
        """
        logger.info(f"Retrieving papers for query: {query[:100]}...")
        logger.debug(f"Search mode: {'hybrid' if use_hybrid else 'bm25'}, top_k: {top_k}")

        # Generate query embedding
        logger.debug("Generating query embedding...")
        query_embedding = await embeddings_client.embed_query(query)
        logger.debug(f"Generated embedding with {len(query_embedding)} dimensions")

        # Search using OpenSearch
        logger.debug("Searching OpenSearch...")
        search_results = opensearch_client.search_unified(
            query=query, 
            query_embedding=query_embedding, 
            size=top_k, 
            use_hybrid=use_hybrid, 
        )

        hits = search_results.get("hits", [])
        logger.info(f"Found {len(hits)} documents from OpenSearch")

        chunks: List[dict[str, Any]] = []
        for hit in hits:
            chunks.append(
                {
                    "page_content": hit["chunk_text"],
                    "metadata": {
                        "arxiv_id": hit["arxiv_id"],
                        "title": hit.get("title", ""),
                        "authors": hit.get("authors", ""),
                        "score": hit.get("score", 0.0),
                        "source": f"https://arxiv.org/pdf/{hit['arxiv_id']}.pdf",
                        "section": hit.get("section_title") or hit.get("section_name") or "",
                        "search_mode": "hybrid" if use_hybrid else "bm25",
                        "top_k": top_k,
                    },
                }
            )

        logger.debug(f"Built {len(chunks)} retrieval chunks for tool payload")
        logger.info(f"Retrieved {len(chunks)} papers successfully")

        return chunks

    return retrieve_papers
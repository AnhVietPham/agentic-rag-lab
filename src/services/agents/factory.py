from typing import Optional

from src.services.embeddings.jina_client import JinaEmbeddingsClient
from src.services.langfuse.client import LangfuseTracer
from src.services.llm.client import LLMClient
from src.services.opensearch.client import OpenSearchClient

from .agentic_rag import AgenticRAGService
from .config import GraphConfig

def make_agentic_rag_service(
    opensearch_client: OpenSearchClient,
    llm_client: LLMClient,
    embeddings_client: JinaEmbeddingsClient,
    langfuse_tracer: Optional[LangfuseTracer] = None,
    top_k: int = 3, 
    use_hybrid: bool = True,
    model: str = "llama3.2:1b",
) -> AgenticRAGService: 
    graph_config = GraphConfig(
        top_k=top_k,
        use_hybrid=use_hybrid,
        model=model,
    )

    return AgenticRAGService(
        opensearch_client=opensearch_client,
        llm_client=llm_client,
        embeddings_client=embeddings_client,
        langfuse_tracer=langfuse_tracer,
        graph_config=graph_config
    )
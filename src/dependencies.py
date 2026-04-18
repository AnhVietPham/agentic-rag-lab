from typing import TYPE_CHECKING, Annotated, Generator

if TYPE_CHECKING:
    from fastapi import Depends, Request
    from sqlalchemy.orm import Session
else: 
    try: 
        from fastapi import Depends, Request
        from sqlalchemy.orm import Session
    except ImportError:
        pass

from src.config import Settings
from src.db.interfaces.base import BaseDatabase
from src.services.arxiv.client import ArxivClient
from src.services.cache.client import CacheClient
from src.services.embeddings.jina_client import JinaEmbeddingsClient
from src.services.langfuse.client import LangfuseTracer
from src.services.llm.client import LLMClient
from src.services.opensearch.client import OpenSearchClient
from src.services.pdf_parser.parser import PDFParserService
from src.services.agents.agentic_rag import AgenticRAGService
from src.services.agents.factory import make_agentic_rag_service

def get_settings() -> Settings:
    """Load settings from environment and `.env` (do not cache — must match app lifespan)."""
    return Settings()


def get_app_settings(request: Request) -> Settings:
    """Same Settings instance as startup (includes OPENROUTER_API_KEY from server .env when set)."""
    return request.app.state.settings


def get_request_settings(request: Request) -> Settings:
    """Alias for `get_app_settings`."""
    return request.app.state.settings

def get_database(request: Request) -> BaseDatabase: 
    """Get database from the request state."""
    return request.app.state.database

def get_db_session(database: Annotated[BaseDatabase, Depends(get_database)]) -> Generator[Session, None, None]:
    """Get a database session."""
    with database.get_session() as session:
        yield session

def get_opensearch_client(request: Request) -> OpenSearchClient:
    """Get OpenSearch client from the request state."""
    return request.app.state.opensearch_client

def get_arxiv_client(request: Request) -> ArxivClient:
    """Get Arxiv client from the request state."""
    return request.app.state.arxiv_client

def get_pdf_parser(request: Request) -> PDFParserService:
    """Get PDF parser from the request state."""
    return request.app.state.pdf_parser

def get_embeddings_service(request: Request) -> JinaEmbeddingsClient:
    """Get embeddings service from the request state."""
    return request.app.state.embeddings_service

def get_llm_client(request: Request) -> LLMClient:
    """Get unified LLM client (OpenRouter) from app state."""
    return request.app.state.llm_client

def get_langfuse_tracer(request: Request) -> LangfuseTracer:
    """Get Langfuse tracer from the request state."""
    return request.app.state.langfuse_tracer

def get_cache_client(request: Request) -> CacheClient | None: 
    """Get cache client from the request state."""
    return getattr(request.app.state, "cache_client", None)

# Dependency annotations
SettingsDep = Annotated[Settings, Depends(get_settings)]
AppSettingsDep = Annotated[Settings, Depends(get_app_settings)]
DatabaseDep = Annotated[BaseDatabase, Depends(get_database)]
SessionDep = Annotated[Session, Depends(get_db_session)]
OpenSearchDep = Annotated[OpenSearchClient, Depends(get_opensearch_client)]
ArxivDep = Annotated[ArxivClient, Depends(get_arxiv_client)]
PDFParserDep = Annotated[PDFParserService, Depends(get_pdf_parser)]
EmbeddingsDep = Annotated[JinaEmbeddingsClient, Depends(get_embeddings_service)]
LLMDep = Annotated[LLMClient, Depends(get_llm_client)]
LangfuseDep = Annotated[LangfuseTracer, Depends(get_langfuse_tracer)]
CacheDep = Annotated[CacheClient | None, Depends(get_cache_client)]

def get_agentic_rag_service(
    opensearch: OpenSearchDep,
    llm: LLMDep,
    embeddings: EmbeddingsDep,
    langfuse: LangfuseDep,
) -> AgenticRAGService:
    """Get agentic RAG service from the request state."""
    return make_agentic_rag_service(
        opensearch_client=opensearch,
        llm_client=llm,
        embeddings_client=embeddings,
        langfuse_tracer=langfuse,
        model=llm.default_chat_model,
    )

AgenticRAGDep = Annotated[AgenticRAGService, Depends(get_agentic_rag_service)]

# Backward-compatible aliases (prefer LLMDep / get_llm_client)
OllamaDep = LLMDep
get_ollama_client = get_llm_client


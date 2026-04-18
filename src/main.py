import logging 
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from src.config import ENV_FILE_PATH, get_settings
from src.db.factory import make_database
from src.routers import agentic_ask, hybrid_search, ping
from src.routers.ask import ask_router, stream_router
from src.services.arxiv.factory import make_arxiv_client
from src.services.cache.factory import make_cache_client
from src.services.embeddings.factory import make_embeddings_service
from src.services.langfuse.factory import make_langfuse_tracer
from src.services.llm.client import LLMClient
from src.services.llm.factory import make_llm_client
from src.services.opensearch.factory import make_opensearch_client
from src.services.pdf_parser.factory import make_pdf_parser_service
# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan for the API.
    """

    logger.info("Starting RAG API...")

    settings = get_settings()
    app.state.settings = settings

    logger.info(
        "Config: .env path=%s exists=%s",
        ENV_FILE_PATH,
        ENV_FILE_PATH.is_file(),
    )
    logger.info(
        "OPENROUTER_API_KEY loaded (non-empty): %s",
        bool(str(settings.openrouter_api_key or "").strip()),
    )

    _llm = LLMClient(settings)
    logger.info(
        "LLM provider=%s default_model=%s (/ask, /ask-agentic, LangGraph)",
        _llm.provider_name,
        _llm.default_chat_model,
    )

    database = make_database()
    app.state.database = database
    logger.info("Database connected")

    # Initialize search service
    opensearch_client = make_opensearch_client()
    app.state.opensearch_client = opensearch_client

    # Verify OpenSearch connectivity and create index if needed
    if opensearch_client.health_check():
        logger.info("OpenSearch connected successfully")

        # Setup hybrid index (supports all search types)
        setup_results = opensearch_client.setup_indices(force=False)
        if setup_results.get("hybrid_index"): 
            logger.info("Hybrid index created")
        else: 
            logger.info("Hybrid index already exists")
        
        # Get simple statistics
        try:
            stats = opensearch_client.client.count(index=opensearch_client.index_name)
            logger.info(f"OpenSearch ready: {stats['count']} documents indexed")
        except Exception: 
            logger.info("OpenSearch index ready (stats unavailable)")
    else:
        logger.warning("OpenSearch connection failed - search features will be limited")
    
    # Initialize other services (kept for future endpoints and notebook demos)
    app.state.arxiv_client = make_arxiv_client()
    app.state.pdf_parser = make_pdf_parser_service()
    app.state.embeddings_service = make_embeddings_service()
    app.state.llm_client = make_llm_client(settings)
    app.state.langfuse_tracer = make_langfuse_tracer()
    app.state.cache_client = make_cache_client(settings)
    # logger.info("Services initialized: arXiv API client, PDF parser, OpenSearch, Embeddings, Ollama, Langfuse, Cache")

    logger.info("API ready")
    yield

    # database.teardown()
    logger.info("API shutdown complete")

app = FastAPI(
    title="Production Agentic RAG API",
    description="API for the production agentic RAG system",
    version=os.getenv("APP_VERSION", "0.1.0"),
    lifespan=lifespan,
)

# Include routers
app.include_router(ping.router, prefix="/api/v1")  # Health check endpoint
app.include_router(hybrid_search.router, prefix="/api/v1")  # Search chunks with BM25/hybrid
app.include_router(ask_router, prefix="/api/v1")  # RAG question answering with LLM
app.include_router(stream_router, prefix="/api/v1")  # Streaming RAG responses
app.include_router(agentic_ask.router)  # Agentic RAG with intelligent retrieval

if __name__ == "__main__": 
    uvicorn.run("src.main:app", port=8001, host="0.0.0.0", reload=True, reload_dirs=["src"])




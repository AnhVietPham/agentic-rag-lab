import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE_PATH = PROJECT_ROOT / ".env"

# Ensure .env is applied to os.environ before any Settings() (uvicorn cwd may differ from project root).
if ENV_FILE_PATH.is_file():
    load_dotenv(ENV_FILE_PATH, override=False)

class BaseConfigSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        extra="ignore",
        frozen=True,
        env_nested_delimiter="__",
        case_sensitive=False
    )

class ArxivSettings(BaseConfigSettings): 
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="ARXIV__",
        extra="ignore",
        frozen=True,
        case_sensitive=False
    )

    base_url: str = "https://export.arxiv.org/api/query"
    pdf_cache_dir: str = "./data/arxiv_pdfs"
    rate_limit_delay: float = 3.0
    timeout_seconds: int = 30
    max_results: int = 15
    search_category: str = "cs.AI"
    download_max_retries: int = 3
    download_retry_delay_base: float = 5.0
    max_concurrent_downloads: int = 5
    max_concurrent_parsing: int = 3

    namespaces: dict = {
        "atom": "http://www.w3.org/2005/Atom",
        "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
        "arxiv": "http://arxiv.org/schemas/atom",
    }

    @field_validator("pdf_cache_dir")
    @classmethod
    def validate_cache_dir(cls, v: str) -> str: 
        os.makedirs(v, exist_ok=True)
        return v

class PDFParserSettings(BaseConfigSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="PDF_PARSER__",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    max_pages: int = 30
    max_file_size_mb: int = 20
    do_ocr: bool = False
    do_table_structure: bool = True

class ChunkingSettings(BaseConfigSettings): 
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="CHUNKING__",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )


    chunk_size: int = 600
    overlap_size: int = 100
    min_chunk_size: int = 100
    section_based: bool = True

class OpenSearchSettings(BaseConfigSettings): 
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="OPENSEARCH__",
        extra="ignore",
        frozen=True,
        case_sensitive=False
    )

    host: str = "http://localhost:9201"
    index_name: str = "production-agentic-rag-papers"
    chunk_index_suffix: str = "chunks"
    max_test_size: int = 1000000

    # Vector search settings
    vector_dimension: int = 1024
    vector_space_type: str = "cosinesimil"

    # Hybrid search settings
    rrf_pipeline_name: str = "hybrid-rrf-pipeline"
    hybrid_search_size_multiplier: int = 2

class LangfuseSettings(BaseConfigSettings): 
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        # Single underscore after LANGFUSE so .env matches LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY, …
        env_prefix="LANGFUSE_",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    public_key: str = ""
    secret_key: str = ""
    host: str = "http://localhost:3000"  # Self-hosted Langfuse URL
    enabled: bool = True
    flush_at: int = 15  # Number of events before flushing
    flush_interval: float = 1.0  # Seconds between flushes
    max_retries: int = 3
    timeout: int = 30
    debug: bool = False

class RedisSettings(BaseConfigSettings): 
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="REDIS__",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    host: str = "localhost"
    port: int = 6379
    password: str = ""
    db: int = 0
    decode_responses: bool = True
    socket_timeout: int = 30
    socket_connect_timeout: int = 30

    # Cache settings
    ttl_hours: int = 6  # Cache TTL in hours

class GuardsSettings(BaseConfigSettings): 
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="GUARDS__",
        extra="ignore",
        frozen=True,
        case_sensitive=False
    )

    max_input_length: int = 1000
    enable_injection_check: bool = True
    enable_disclaimer: bool = True

class Settings(BaseConfigSettings):
    app_version: str = "0.1.0"
    debug: bool = True
    environment: Literal["development", "staging", "production"] = "development"
    service_name: str = "production-agentic-rag-api"

    postgres_database_url: str = "postgresql+psycopg2://production_agentic_rag_user:production_agentic_rag_password@localhost:5433/production_agentic_rag_db"
    postgres_echo_sql: bool = False
    postgres_pool_size: int = 20
    postgres_max_overflow: int = 0

    # LLM HTTP timeout (seconds). Still accepts legacy env name OLLAMA_TIMEOUT.
    llm_http_timeout_seconds: int = Field(
        default=300,
        validation_alias=AliasChoices("LLM_HTTP_TIMEOUT_SECONDS", "OLLAMA_TIMEOUT"),
    )

    # OpenRouter (OpenAI-compatible): RAG, streaming, LangGraph
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_http_referer: str = ""
    openrouter_app_title: str = "production-agentic-rag-api"
    openrouter_model: str = Field(
        default="openai/gpt-4o-mini",
        validation_alias=AliasChoices("OPENROUTER_MODEL"),
    )
    # Optional: different OpenRouter slug for translation-style tasks. Falls back to `openrouter_model` when empty.
    openrouter_translation_model: str = Field(
        default="",
        validation_alias=AliasChoices("OPENROUTER_TRANSLATION_MODEL", "TRANSLATION_MODEL"),
    )

    jina_api_key: str = ""

    arxiv: ArxivSettings = Field(default_factory=ArxivSettings)
    pdf_parser: PDFParserSettings = Field(default_factory=PDFParserSettings)
    chunking: ChunkingSettings = Field(default_factory=ChunkingSettings)
    opensearch: OpenSearchSettings = Field(default_factory=OpenSearchSettings)
    langfuse: LangfuseSettings = Field(default_factory=LangfuseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)


def get_settings() -> Settings:
    return Settings()

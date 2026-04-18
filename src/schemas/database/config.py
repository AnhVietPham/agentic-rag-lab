from pydantic import Field
from pydantic_settings import BaseSettings

class PostgresSettings(BaseSettings):
    """Settings for the PostgreSQL database."""

    database_url: str = Field(
        default="postgresql+psycopg2://production_agentic_rag_user:production_agentic_rag_password@localhost:5433/production_agentic_rag_db",
        description="PostgreSQL database URL"
    )
    echo_sql: bool = Field(default=False, description="Enable SQL query logging")
    pool_size: int = Field(default=20, description="Database connection pool size")
    max_overflow: int = Field(default=0, description="Maximum pool overflow")

    class Config:
        env_prefix = "POSTGRES_"
import sys
from pathlib import Path
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "dags"))

@pytest.fixture(autouse=True)
def clear_lru_cache():
    """Clear lru_cache on get_cached_services between tests to avoid shared state."""
    yield
    try: 
        from arxiv_ingestion.common import get_cached_services
        get_cached_services.cache_clear()
    except Exception: 
        pass

@pytest.fixture
def mock_airflow_context(): 
    """"Fake Airflow context with a mock TaskInstance for XCom operations."""
    ti = MagicMock()
    ti.xcom_push = MagicMock()
    ti.xcom_pull = MagicMock(return_value=None)
    return {
        "execution_date": datetime(2026, 2, 10),
        "ti": ti,
    }

@pytest.fixture
def mock_database(): 
    """"Mock database with a context-manager session."""
    database = MagicMock()
    session = MagicMock()
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=session)
    ctx.__exit__ = MagicMock(return_value=False)
    database.get_session = ctx
    return database, session

@pytest.fixture
def mock_opensearch_client(): 
    """Mock OpenSearch client with health check and index operations."""
    client = MagicMock()
    client.index_name = "arxiv_papers"
    client.health_check.return_value = True
    client.client.cluster.health.return_value = {"status": "green"}
    client.client.count.return_value = {"count": 100}
    client.client.indices.stats.return_value = {
        "indices": {
            "arxiv_papers": {
                "total": {"store": {"size_in_bytes": 2_097_152}}  # 2 MB
            }
        }
    }
    client.client.search.return_value = {
        "aggregations": {
            "unique_papers": {
                "value": 10
            }
        }
    }
    client.setup_indices.return_value = {
        "hybrid_index": True,
        "rrf_pipeline": True,
    }
    return client

@pytest.fixture
def mock_arxiv_client(): 
    """Mock arXiv client."""
    client = MagicMock()
    client.max_results = 10
    client.base_url = "https://export.arxiv.org"
    return client

@pytest.fixture
def mock_metadata_fetcher(): 
    """Mock async metadata fetcher."""
    fetcher = MagicMock()
    fetcher.fetch_and_process_papers.return_value = {
        "papers_fetched": 5,
        "papers_stored": 5,
    }
    return fetcher

@pytest.fixture
def mock_all_services(mock_arxiv_client, mock_database, mock_metadata_fetcher, mock_opensearch_client):
    """Bundle all mock services into the tuple returned by get_cached_services()."""
    database, _session = mock_database
    pdf_parser = MagicMock()
    return (mock_arxiv_client, pdf_parser, database, mock_metadata_fetcher, mock_opensearch_client)

@pytest.fixture
def sample_fetch_results(): 
    return {
        "papers_fetched": 5,
        "papers_stored": 5,
        "date": "20260209",
    }

@pytest.fixture
def sample_hybrid_stats(): 
    return {
        "papers_processed": 5,
        "total_chunks_created": 50, 
        "total_chunks_indexed": 50,
        "total_embeddings_generated": 50
    }

@pytest.fixture
def mock_paper(): 
    """Single mock Paper ORM object."""
    paper = MagicMock()
    paper.id = 1
    paper.arxiv_id = "2508.00001"
    paper.title = "Test Paper on AI"
    paper.authors = "John Doe, Jane Smith"
    paper.abstract = "This is a test abstract."
    paper.categories = "cs.AI"
    paper.published_date = "2025-08-09"
    paper.raw_text = "Full text content of the paper for chunking."
    paper.sections = {"introduction": "Intro text", "conclusion": "Conclusion text"}
    paper.created_at = datetime(2025, 8, 9, 12, 0, 0)
    return paper
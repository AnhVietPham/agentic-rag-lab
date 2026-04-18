from src.config import get_settings

from .client import ArxivClient

def make_arxiv_client() -> ArxivClient: 
    settings = get_settings()

    client = ArxivClient(settings=settings.arxiv)

    return client
import asyncio
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db.factory import make_database
from src.models.paper import Paper
from src.services.indexing.factory import make_hybrid_indexing_service

def paper_to_dict(paper: Paper) -> dict: 
    """Convert Paper ORM to dict expected by HybridIndexingService (same as DAG)"""

    return {
        "id": str(paper.id),
        "arxiv_id": paper.arxiv_id,
        "title": paper.title,
        "authors": paper.authors,
        "abstract": paper.abstract,
        "categories": paper.categories,
        "published_date": paper.published_date,
        "raw_text": paper.raw_text,
        "sections": paper.sections
    }

async def index_papers_from_db(limit: int | None = None, arxiv_id: str | None = None) -> dict: 
    """
    Load papers from DB and index into OpenSearch.
    - If arxiv_id: index only that paper.
    - Else: index all papers (or up to `limit`).
    """
    database = make_database()
    database.startup()

    with database.get_session() as session: 
        if arxiv_id: 
            paper = session.query(Paper).filter(Paper.arxiv_id == arxiv_id).first()
            if not paper: 
                print(f"No paper found with arxiv_id: {arxiv_id}")
                return {"papers_processed": 0, "total_chunks_created": 0}
            papers = [paper]
        else: 
            query = session.query(Paper).order_by(Paper.created_at.desc())
            if limit: 
                query = query.limit(limit)
            papers = query.all()

        if not papers: 
            print("No papers to index.")
            return {"papers_processed": 0, "total_chunks_created": 0}
        
        papers_data = [paper_to_dict(paper) for paper in papers]
    
    indexing_service = make_hybrid_indexing_service()
    stats = await indexing_service.index_papers_batch(papers_data, replace_existing=True)

    return stats

def main():
    parser = argparse.ArgumentParser(description="Index papers from DB into OpenSearch")
    parser.add_argument("--limit", type=int, default=None, help="Max number of papers (default: all)")
    parser.add_argument("--arxiv-id", type=str, default=None, help="Index only this arxiv_id")
    args = parser.parse_args()
    stats = asyncio.run(index_papers_from_db(limit=args.limit, arxiv_id=args.arxiv_id))
    print("Indexing complete:")
    print(f"  Papers processed: {stats['papers_processed']}")
    print(f"  Chunks indexed:   {stats['total_chunks_indexed']}")
    print(f"  Errors:           {stats['total_errors']}")
if __name__ == "__main__":
    main()
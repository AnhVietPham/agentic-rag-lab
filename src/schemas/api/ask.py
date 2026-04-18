from typing import List, Optional
from pydantic import BaseModel, Field

class AskRequest(BaseModel): 
    """Request model for RAG question answering."""

    query: str = Field(..., description="User's question", min_length=1, max_length=1000)
    top_k: int = Field(3, description="Number of top chunks top retrieve", ge=1, le=10)
    use_hybrid: bool = Field(True, description="Use hybrid search (BM25 + vector)")
    model: str = Field(
        "openai/gpt-4o-mini",
        description="OpenRouter model id (e.g. openai/gpt-4o-mini). Matches server default unless you override per request.",
    )
    categories: Optional[List[str]] = Field(None, description="Filter by arXiv categories")

    class Config: 
        json_schema_extra = {
            "example": {
                "query": "What are transformers in machine learning?", 
                "top_k": 3,
                "use_hybrid": True,
                "model": "openai/gpt-4o-mini",
                "categories": ["cs.CV", "cs.LG"]
            }
        }

class AskResponse(BaseModel): 
    query: str = Field(..., description="Original user question")
    answer: str = Field(..., description="Generated answer from LLM")
    sources: List[str] = Field(..., description="PDF URLs of source papers")
    chunks_used: int = Field(..., description="Number of chunks used for generation")
    search_mode: str = Field(..., description="Search mode used: bm25 or hybrid")

    class Config: 
        json_schema_extra = {
            "example": {
                "query": "What are transformers in machine learning?",
                "answer": "Transformers are a neural network architecture...",
                "sources": ["https://arxiv.org/pdf/1706.03762.pdf", "https://arxiv.org/pdf/1810.04805.pdf"],
                "chunks_used": 3,
                "search_mode": "hybrid",
            }
        }


class AgenticPaperSource(BaseModel):
    """One retrieved paper cited by the agentic RAG path."""

    arxiv_id: str = Field(..., description="arXiv id")
    title: str = Field(..., description="Paper title")
    authors: List[str] = Field(default_factory=list, description="Author names")
    url: str = Field(..., description="PDF or abs URL")
    relevance_score: float = Field(0.0, description="Retrieval relevance score")


class AgenticAskResponse(AskResponse):
    """Response model for agentic RAG question answering."""

    # Overrides AskResponse.sources (List[str]): agentic pipeline returns structured metadata
    sources: List[AgenticPaperSource] = Field(
        default_factory=list,
        description="Papers retrieved and graded as relevant",
    )
    reasoning_steps: List[str] = Field(..., description="Agent's decision-making steps")
    retrieval_attempts: int = Field(..., description="Number of document retrieval attempts")
    trace_id: Optional[str] = Field(None, description="Langfuse trace ID for feedback and debugging")

    class Config:
        json_schema_extra = {
            "example": {
                "query": "What are transformers in machine learning?",
                "answer": "Transformers are neural network architectures...",
                "sources": [
                    {
                        "arxiv_id": "1706.03762",
                        "title": "Attention Is All You Need",
                        "authors": ["Vaswani et al."],
                        "url": "https://arxiv.org/pdf/1706.03762.pdf",
                        "relevance_score": 0.95,
                    }
                ],
                "chunks_used": 3,
                "search_mode": "hybrid",
                "reasoning_steps": [
                    "Decided to retrieve relevant papers",
                    "Retrieved documents from database",
                    "Generated answer from relevant documents",
                ],
                "retrieval_attempts": 1,
                "trace_id": "abc123-def456-ghi789",
            }
        }

class FeedbackRequest(BaseModel): 
    """Request model for user feedback on RAG answers."""

    trace_id: str = Field(..., description="Langfuse trace ID from the response")
    score: float = Field(..., description="Feedback score (0-1 or -1 to 1)", ge=-1, le=1)
    comment: Optional[str] = Field(None, description="Optional feedback comment", max_length=1000)

    class Config: 
        json_schema_extra = { 
            "example": {
                "trace_id": "abc123-def456-ghi789",
                "score": 1.0,
                "comment": "This answer was very helpful and accurate!",
            }
        }

class FeedbackResponse(BaseModel): 
    """Response model for feedback submission."""
    success: bool = Field(..., description="Whether feedback was recorded successfully")
    message: str = Field(..., description="Status message")

    class Config: 
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Feedback recorded successfully",
            }
        }
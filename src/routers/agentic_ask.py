from fastapi import APIRouter, HTTPException
from src.dependencies import AgenticRAGDep, LangfuseDep
from src.schemas.api.ask import AgenticAskResponse, AskRequest, FeedbackRequest, FeedbackResponse

router = APIRouter(prefix="/api/v1", tags=["agentic-rag"])

@router.post("/ask-agentic", response_model=AgenticAskResponse)
async def ask_agentic(
    request: AskRequest, 
    agentic_rag: AgenticRAGDep
) -> AgenticAskResponse: 
    try: 
        result = await agentic_rag.ask(request.query, model=request.model)

        return AgenticAskResponse(
            query=result["query"], 
            answer=result["answer"], 
            sources=result.get("sources", []), 
            chunks_used=request.top_k, 
            search_mode="hybrid" if request.use_hybrid else "bm25", 
            reasoning_steps=result.get("reasoning_steps", []),
            retrieval_attempts=result.get("retrieval_attempts", 0),
            trace_id=result.get("trace_id"),
        )
    
    except ValueError as e: 
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e: 
        raise HTTPException(status_code=500, detail=f"Error processing question: {str(e)}")

@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    request: FeedbackRequest,
    langfuse_tracer: LangfuseDep,
) -> FeedbackResponse:
    try: 
        if not langfuse_tracer:
            raise HTTPException(
                status_code=503,
                detail="Langfuse tracing is disabled. Cannot submit feedback."
            )

        success = langfuse_tracer.submit_feedback(
            trace_id=request.trace_id,
            score=request.score,
            comment=request.comment
        ) 

        if success: 
            langfuse_tracer.flush()

            return FeedbackResponse(
                success=True,
                message="Feedback submitted successfully",
            )
        else: 
            raise HTTPException(
                status_code=500,
                detail="Failed to submit feedback to Langfuse"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error submitting feedback: {str(e)}"
        )

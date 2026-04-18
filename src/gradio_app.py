import json
import logging
import os
from pathlib import Path
from typing import Iterator

import gradio as gr
import httpx

logger = logging.getLogger(__name__)

# Load .env from project root (same keys as API: OPENROUTER_MODEL, optional GRADIO_API_BASE_URL)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"
if _ENV_FILE.is_file():
    try:
        from dotenv import load_dotenv

        load_dotenv(_ENV_FILE, override=False)
    except ImportError:
        pass

# Must match OpenRouter model slugs (not Ollama names). Server uses `effective_rag_model(request.model)`.
_DEFAULT_OPENROUTER_MODEL = "openai/gpt-4o-mini"
API_BASE_URL = os.environ.get("GRADIO_API_BASE_URL", "http://localhost:8001/api/v1").rstrip("/")
DEFAULT_MODEL = (os.environ.get("OPENROUTER_MODEL") or _DEFAULT_OPENROUTER_MODEL).strip() or _DEFAULT_OPENROUTER_MODEL

# Common OpenRouter slugs; users can type any slug when allow_custom_value is True
OPENROUTER_MODEL_CHOICES = [
    "openai/gpt-4o-mini",
    "openai/gpt-4o",
    "anthropic/claude-3.5-sonnet",
    "meta-llama/llama-3.2-3b-instruct",
    "mistralai/mistral-7b-instruct",
]
AVAILABLE_CATEGORIES = ["cs.AI", "cs.LG"]

async def stream_response(
    query: str, 
    top_k: int = 3, 
    use_hybrid: bool = True, 
    model: str = DEFAULT_MODEL, 
    categories: str = ""
) -> Iterator[str]: 
    """Stream response from the RAG API."""
    if not query.strip(): 
        yield "Please enter a question."
        return
    
    # Parse categories
    category_list = [cat.strip() for cat in categories.split(",") if cat.strip()] if categories else None

    # Prepare request payload
    payload = {
        "query": query,
        "top_k": top_k,
        "use_hybrid": use_hybrid,
        "model": model,
        "categories": category_list,
    }

    try: 
        url = f"{API_BASE_URL}/stream"
        async with httpx.AsyncClient(timeout=60.0) as client: 
            async with client.stream("POST", url, json=payload, headers={"Accept": "text/event-stream"}) as response: 
                if response.status_code != 200: 
                    yield f"Error: API returned status {response.status_code}"
                    return
                
                current_answer = ""
                sources = []
                chunks_used = 0
                search_mode = ""

                async for line in response.aiter_lines(): 
                    if line.startswith("data: "): 
                        data_str = line[6:]
                        try: 
                            data = json.loads(data_str)

                            # Handle error
                            if "error" in data: 
                                yield f"Error: {data['error']}"
                                return
                            
                            # Handle metadata
                            if "sources" in data: 
                                sources = data["sources"]
                                chunks_used = data["chunks_used"]
                                search_mode = data["search_mode"]
                                continue
                            
                            # Handle streaming chunks
                            if "chunk" in data: 
                                current_answer += data["chunk"]
                                # Format response with sources if we have them
                                formatted_response = current_answer
                                if sources or chunks_used: 
                                    formatted_response += f"\n\n**Search Info:**\n"
                                    formatted_response += f"- Mode: {search_mode}\n"
                                    formatted_response += f"- Chunks Used: {chunks_used}\n"
                                    if sources: 
                                        formatted_response += f"- Sources: {len(sources)} papers\n"
                                        for i, source in enumerate(sources[:3], 1):  # Show first 3 sources
                                            formatted_response += f"  {i}. [{source.split('/')[-1]}]({source})\n"
                                        if len(sources) > 3:
                                            formatted_response += f"  ... and {len(sources) - 3} more\n"
                                yield formatted_response
                            
                            # Handle completion
                            if data.get("done", False):
                                final_answer = data.get("answer", current_answer)
                                if final_answer != current_answer:
                                    current_answer = final_answer

                                # Final formatted response
                                formatted_response = current_answer
                                if sources or chunks_used:
                                    formatted_response += f"\n\n**Search Info:**\n"
                                    formatted_response += f"- Mode: {search_mode}\n"
                                    formatted_response += f"- Chunks used: {chunks_used}\n"
                                    if sources:
                                        formatted_response += f"- Sources: {len(sources)} papers\n"
                                        for i, source in enumerate(sources[:3], 1):
                                            formatted_response += f"  {i}. [{source.split('/')[-1]}]({source})\n"
                                        if len(sources) > 3:
                                            formatted_response += f"  ... and {len(sources) - 3} more\n"

                                yield formatted_response
                                break
                        except json.JSONDecodeError:
                            continue
    except httpx.RequestError as e:
        yield f"Connection error: {str(e)}\nMake sure the API server is running at {API_BASE_URL}"
    except Exception as e:
        yield f"Unexpected error: {str(e)}"


async def agentic_response(
    query: str,
    top_k: int = 3,
    use_hybrid: bool = True,
    model: str = DEFAULT_MODEL,
    categories: str = "",
) -> str:
    """Call LangGraph agentic RAG (`POST /api/v1/ask-agentic`)."""
    if not query.strip():
        return "Please enter a question."

    category_list = [cat.strip() for cat in categories.split(",") if cat.strip()] if categories else None
    payload = {
        "query": query,
        "top_k": top_k,
        "use_hybrid": use_hybrid,
        "model": model,
        "categories": category_list,
    }
    url = f"{API_BASE_URL}/ask-agentic"

    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(url, json=payload)
    except httpx.RequestError as e:
        return (
            f"**Connection error:** {e}\n\n"
            f"Ensure the API is running and `GRADIO_API_BASE_URL` points to it (default `{API_BASE_URL}`)."
        )

    if response.status_code != 200:
        detail: str
        try:
            body = response.json()
            detail = str(body.get("detail", body))
        except Exception:
            detail = response.text or "(empty body)"
        return f"**Error** (`{response.status_code}`): {detail}"

    try:
        data = response.json()
    except json.JSONDecodeError:
        return "**Error:** Invalid JSON from API."

    answer = data.get("answer", "")
    lines = [answer.strip() if answer else "_No answer._"]

    steps = data.get("reasoning_steps") or []
    if steps:
        lines.append("\n---\n**Reasoning steps**\n")
        for i, step in enumerate(steps, 1):
            lines.append(f"{i}. {step}")

    attempts = data.get("retrieval_attempts")
    if attempts is not None:
        lines.append(f"\n**Retrieval attempts:** {attempts}")

    mode = data.get("search_mode", "")
    chunks = data.get("chunks_used", "")
    if mode or chunks != "":
        lines.append(f"\n**Search:** mode={mode}, top_k (chunks_used field)={chunks}")

    sources = data.get("sources") or []
    if sources:
        lines.append("\n---\n**Sources**\n")
        for i, src in enumerate(sources, 1):
            if isinstance(src, dict):
                title = src.get("title") or src.get("arxiv_id") or "Paper"
                url_s = src.get("url") or ""
                aid = src.get("arxiv_id", "")
                score = src.get("relevance_score")
                authors = src.get("authors") or []
                auth_s = ", ".join(authors) if isinstance(authors, list) else str(authors)
                score_s = f" (score: {score:.3f})" if isinstance(score, (int, float)) else ""
                if url_s:
                    lines.append(f"{i}. [{title}]({url_s}) — `{aid}`{score_s}")
                else:
                    lines.append(f"{i}. **{title}** — `{aid}`{score_s}")
                if auth_s:
                    lines.append(f"   _{auth_s}_")
            else:
                lines.append(f"{i}. {src}")

    tid = data.get("trace_id")
    if tid:
        lines.append(f"\n**Langfuse trace_id:** `{tid}`")

    return "\n".join(lines)


def create_gradio_interface():
    """Create and configure the Gradio interface."""

    with gr.Blocks(
        title="arXiv Paper Curator - Chat Bot",
        theme=gr.themes.Soft(),
    ) as interface:
        gr.Markdown(
            """
            # arXiv Paper Curator — RAG Chat

            **Traditional RAG** streams tokens from `/api/v1/stream` (retrieve → answer).

            **Agentic RAG** runs the LangGraph pipeline via `/api/v1/ask-agentic` (guardrail → retrieve → grade → …).
            """
        )

        with gr.Row():
            with gr.Column(scale=3):
                query_input = gr.Textbox(
                    label="Your question",
                    placeholder="What are transformers in machine learning?",
                    lines=2,
                    max_lines=5,
                )
            with gr.Column(scale=1):
                gr.Markdown("_Use the button inside each tab below._")

        with gr.Row():
            with gr.Column():
                with gr.Accordion("Advanced options", open=False):
                    top_k = gr.Slider(
                        minimum=1,
                        maximum=10,
                        value=3,
                        step=1,
                        label="top_k",
                        info="Used by classic `/stream` retrieve. Agentic graph uses server GraphConfig (not this slider) unless you change the API.",
                    )

                    use_hybrid = gr.Checkbox(
                        value=True,
                        label="use_hybrid",
                        info="Classic streaming search. Agentic service uses its own hybrid flag from GraphConfig.",
                    )

                    model_choice = gr.Dropdown(
                        choices=(
                            OPENROUTER_MODEL_CHOICES
                            if DEFAULT_MODEL in OPENROUTER_MODEL_CHOICES
                            else [DEFAULT_MODEL, *OPENROUTER_MODEL_CHOICES]
                        ),
                        value=DEFAULT_MODEL,
                        label="OpenRouter model",
                        info="OpenRouter slug. Both APIs: classic uses it for generation; agentic passes it to the graph LLM.",
                        allow_custom_value=True,
                    )

                    categories = gr.Textbox(
                        label="arXiv categories (optional)",
                        placeholder="cs.AI, cs.LG, cs.CL",
                        info="Comma-separated filters for classic `/stream` only (agentic tool search does not take categories from this request).",
                    )

        gr.Examples(
            examples=[
                ["What are transformers in machine learning?", 3, True, DEFAULT_MODEL, "cs.AI, cs.LG"],
                ["How do convolutional neural networks work?", 5, True, DEFAULT_MODEL, "cs.CV, cs.LG"],
                ["What is attention mechanism in deep learning?", 4, False, DEFAULT_MODEL, "cs.AI"],
                ["Explain reinforcement learning algorithms", 3, True, DEFAULT_MODEL, "cs.LG, cs.AI"],
                ["What are the latest developments in NLP?", 5, True, DEFAULT_MODEL, "cs.CL"],
            ],
            inputs=[query_input, top_k, use_hybrid, model_choice, categories],
        )

        shared_inputs = [query_input, top_k, use_hybrid, model_choice, categories]

        with gr.Tabs():
            with gr.Tab("Traditional RAG (streaming)"):
                stream_btn = gr.Button("Stream answer", variant="primary", size="lg")
                stream_output = gr.Markdown(
                    label="Answer",
                    value="Ask a question, then click **Stream answer**.",
                    height=420,
                    elem_classes=["response-markdown"],
                )

            with gr.Tab("Agentic RAG (LangGraph)"):
                agentic_btn = gr.Button("Run agentic graph", variant="primary", size="lg")
                agentic_output = gr.Markdown(
                    label="Answer",
                    value="Ask a question, then click **Run agentic graph** (slower; guardrail + tools).",
                    height=420,
                    elem_classes=["response-markdown"],
                )

        stream_btn.click(
            fn=stream_response,
            inputs=shared_inputs,
            outputs=[stream_output],
            show_progress=True,
        )
        agentic_btn.click(
            fn=agentic_response,
            inputs=shared_inputs,
            outputs=[agentic_output],
            show_progress=True,
        )

        query_input.submit(
            fn=stream_response,
            inputs=shared_inputs,
            outputs=[stream_output],
            show_progress=True,
        )

        gr.Markdown(
            """
            ---

            **API:** start the FastAPI app (e.g. port 8001). Override base URL with `GRADIO_API_BASE_URL` (must include `/api/v1`).

            **Model:** default from `OPENROUTER_MODEL` in `.env` (OpenRouter slugs).

            **Enter key** runs **streaming** only; use **Run agentic graph** for the LangGraph tab.

            **Categories:** cs.AI, cs.LG, cs.CL, cs.CV, cs.NE, stat.ML, …
            """
        )
    return interface

def main():
    """Main entry point for the Gradio app"""
    print("🚀 Starting arXiv Paper Curator Gradio Interface...")
    print(f"📡 API Base URL: {API_BASE_URL}")
    print(f"🤖 Default OpenRouter model: {DEFAULT_MODEL}")

    interface = create_gradio_interface()

    # Launch the interface
    interface.launch(
        server_name="0.0.0.0",
        server_port=7861,  # Changed to avoid port conflict
        share=True,
        show_error=True,
        quiet=False,
    )


if __name__ == "__main__":
    main()





    
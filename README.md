# production-agentic-rag

A **research and learning** codebase for experimenting with **production-style AI engineering**—not a finished product, but hands-on exploration of patterns you would use when building real systems.

**Focus areas:** LangGraph, Mem0, A2A, HITL, RAGAS, and fine-tuning workflows with **Ollama** (plus the surrounding RAG and guardrail stack below).

## Tech stack

| Area | Technologies |
|------|----------------|
| **API & UI** | FastAPI, Uvicorn, Gradio |
| **Agents & orchestration** | LangGraph, LangChain |
| **Retrieval** | OpenSearch (hybrid search), Jina embeddings, arXiv ingestion |
| **Data & cache** | PostgreSQL, Redis |
| **PDF / documents** | Docling |
| **LLMs** | Ollama, OpenRouter |
| **Observability** | Langfuse |
| **Guardrails** | NeMo Guardrails (Colang) |
| **Pipelines** | Apache Airflow (ingestion DAGs) |
| **Runtime** | Python 3.12+, Docker Compose |

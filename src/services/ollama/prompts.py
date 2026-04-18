import json
import re
from pathlib import Path
from typing import Any, Dict, List

from pydantic import ValidationError
from src.schemas.ollama import RAGResponse

class RAGPromptBuilder: 
    """Builder class for creating RAG prompts."""

    def __init__(self): 
        """Initialize the prompt builder."""
        self.prompts_dir = Path(__file__).parent / "prompts"
        self.system_prompt = self._load_system_prompt()
    
    def _load_system_prompt(self) -> str: 
        prompt_file = self.prompts_dir / "rag_system.txt"
        if not prompt_file.exists(): 
            return (
                "You are an AI assistant specialized in answering questions about "
                "academic papers from arXiv. Base your answer STRICTLY on the provided "
                "paper excerpts."
            )
        return prompt_file.read_text().strip()

    def rag_system_and_user(self, query: str, chunks: List[Dict[str, Any]]) -> tuple[str, str]:
        """Split RAG prompt into Anthropic-style system vs user content."""
        user = "### Context from Papers:\n\n"
        for i, chunk in enumerate(chunks, 1):
            chunk_text = chunk.get("chunk_text", chunk.get("content", ""))
            arxiv_id = chunk.get("arxiv_id", "")
            user += f"[{i}. arXiv:{arxiv_id}]\n{chunk_text}\n\n"
        user += f"### Question:\n{query}\n\n"
        user += (
            "### Answer:\nProvide a natural, conversational response (not JSON) "
            "and cite sources using [arXiv:id] format.\n\n"
        )
        return self.system_prompt, user

    def create_rag_prompt(self, query: str, chunks: List[Dict[str, Any]]) -> str:
        system, user = self.rag_system_and_user(query, chunks)
        return f"{system}\n\n{user}"

    def create_structured_prompt(self, query: str, chunks: List[Dict[str, Any]]) -> Dict[str, Any]: 
        prompt_text = self.create_rag_prompt(query=query, chunks=chunks)

        return {
            "prompt": prompt_text,
            "format": RAGResponse.model_json_schema()
        }

class ResponseParser: 
    @staticmethod
    def parse_structured_response(response: str) -> Dict[str, Any]: 
        try: 
            parsed_json = json.loads(response)
            validated_response = RAGResponse(**parsed_json)
            return validated_response.model_dump()
        except (json.JSONDecodeError, ValidationError): 
            return ResponseParser._extract_json_fallback(response)
    
    @staticmethod
    def _extract_json_fallback(response: str) -> Dict[str, Any]: 
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match: 
            try: 
                parsed = json.loads(json_match.group())
                validated = RAGResponse(**parsed)
                return validated.model_dump()
            except (json.JSONDecodeError, ValidationError): 
                pass

        return {
            "answer": response, 
            "sources": [],
            "confidence": "low",
            "citations": []
        }

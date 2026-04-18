from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

class ParserType(str, Enum):
    """PDF Parser Types"""

    DOCLING = "docling"

class PaperSection(BaseModel):
    """Represents a section of a paper."""

    title: str = Field(..., description="Section title")
    content: str = Field(..., description="Section content")
    level: int = Field(0, description="Section level (0=title, 1=section, etc.)")

class PaperFigure(BaseModel): 
    """Represents a figure in a paper."""

    caption: str = Field(..., description="Figure caption")
    id: str = Field(..., description="Figure identifier")

class PaperTable(BaseModel):
    """Represents a table in a paper."""
    caption: str = Field(..., description="Table caption")
    id: str = Field(..., description="Table identifier")

class PdfContent(BaseModel):
    """PDF-specific content extracted by parsers like Docling."""

    sections: List[PaperSection] = Field(..., description="Sections of the paper")
    figures: List[PaperFigure] = Field(..., description="Figures in the paper")
    tables: List[PaperTable] = Field(..., description="Tables in the paper")
    raw_text: str = Field(..., description="Raw text content of the PDF")
    references: List[str] = Field(default_factory=list, description="References in the paper")
    parser_used: ParserType = Field(..., description="Parser used to extract the content")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata of the PDF")

class ArxivMetadata(BaseModel): 
    """Paper metadata extracted from API."""

    title: str = Field(..., description="Paper title from arXiv")
    authors: List[str] = Field(..., description="Paper authors from arXiv")
    abstract: str = Field(..., description="Paper abstract from arXiv")
    categories: List[str] = Field(..., description="Paper categories from arXiv")
    published: str = Field(..., description="Paper publication date from arXiv")
    pdf_url: str = Field(..., description="Paper PDF URL from arXiv")

class ParsedPaper(BaseModel): 
    """Complete paper data combining arXiv metadata and PDF content."""

    arxiv_metadata: ArxivMetadata = Field(..., description="Arxiv metadata")
    pdf_content: Optional[PdfContent] = Field(None, description="Content extracted from PDF")

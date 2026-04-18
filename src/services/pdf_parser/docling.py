import logging
from pathlib import Path
from typing import Optional

import pypdfium2 as pdfium
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from pydantic import ValidationError
from src.exceptions import PDFParsingException, PDFValidationError, PDFDownloadException, PDFDownloadTimeoutError, PDFCacheException
from src.schemas.pdf_parser.models import PdfContent, ParserType, PaperSection, PaperFigure, PaperTable

logger = logging.getLogger(__name__)

class DoclingParser:
    def __init__(self, max_pages: int, max_file_size_mb: int, do_ocr: bool = False, do_table_structure: bool = True):
        pipeline_options = PdfPipelineOptions(
            do_table_structure=do_table_structure,
            do_ocr=do_ocr
        )
        self._converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)})
        self._warmed_up = False
        self.max_pages = max_pages
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024


    def _warm_up_models(self):
        if not self._warmed_up: 
            self._warmed_up = True
    
    def _validate_pdf(self, pdf_path: Path) -> bool:
        try: 
            if pdf_path.stat().st_size == 0:
                logger.error(f"PDF file is empty: {pdf_path}")
                raise PDFValidationError(f"PDF file is empty: {pdf_path}")
            
            file_size = pdf_path.stat().st_size
            if file_size > self.max_file_size_bytes: 
                logger.warning(
                    f"PDF file size ({file_size / 1024 / 1024:.1f}MB) exceeds limit ({self.max_file_size_bytes / 1024 / 1024:.1f}MB), skipping processing."
                )
                raise PDFValidationError(
                    f"PDF file too large: {file_size / 1024 / 1024:.1f}MB > {self.max_file_size_bytes / 1024 / 1024:.1f}MB"
                )

            with open(pdf_path, "rb") as f:
                header = f.read(8)
                if not header.startswith(b"%PDF-"):
                    logger.error(f"File does not have PDF header: {pdf_path}")
                    raise PDFValidationError(f"File does not have PDF header: {pdf_path}")
            
            pdf_doc = pdfium.PdfDocument(str(pdf_path))
            actual_pages = len(pdf_doc)
            pdf_doc.close()

            if actual_pages > self.max_pages:
                logger.warning(
                    f"PDF has {actual_pages} pages, exceeding limit of {self.max_pages} pages. Skipping processing to avoid performance issues."
                )
                raise PDFValidationError(f"PDF has too many pages: {actual_pages} > {self.max_pages}")
                return True
        except Exception as e:
            logger.error(f"Error validating PDF: {e}")
            raise PDFValidationError(f"Error validating PDF: {e}")

        
    
    async def parse_pdf(self, pdf_path: Path) -> Optional[PdfContent]:
        try: 
            self._validate_pdf(pdf_path)

            self._warm_up_models()

            result = self._converter.convert(str(pdf_path), max_num_pages=self.max_pages, max_file_size=self.max_file_size_bytes)

            doc = result.document

            sections = []
            # Track current section title, content and hierarchy level
            current_section = {"title": "", "content": "", "level": 0}

            # Extract sections from document structure
            for element in doc.texts:
                if hasattr(element, "label") and element.label in ["title", "section_header"]: 
                    if current_section["content"].strip():
                        sections.append(
                            PaperSection(
                                title=current_section["title"],
                                content=current_section["content"].strip(),
                                level=current_section["level"],
                            )
                        )
                    
                    # Map Docling labels to simple hierarchy levels
                    level = 0 if element.label == "title" else 1
                    current_section = {"title": element.text, "content": "", "level": level}
                else: 
                    if hasattr(element, "text") and element.text:
                        current_section["content"] += element.text + "\n"
            
            # Add final section
            if current_section["content"].strip():
                sections.append(
                    PaperSection(
                        title=current_section["title"],
                        content=current_section["content"].strip(),
                        level=current_section["level"],
                    )
                )

            # Build PdfContent, but be robust against validation problems
            try:
                pdf_content = PdfContent(
                    sections=sections,
                    figures=[],
                    tables=[],
                    raw_text=doc.export_to_text(),
                    references=[],
                    parser_used=ParserType.DOCLING,
                    metadata={
                        "source": "docling",
                        "note": "Content extracted from PDF, metadata comes from arXiv API",
                    },
                )
            except ValidationError as ve:
                logger.error(f"PdfContent validation failed, falling back to text-only content: {ve}")
                # Fallback: return content without structured sections/tables/figures
                pdf_content = PdfContent(
                    sections=[],
                    figures=[],
                    tables=[],
                    raw_text=doc.export_to_text(),
                    references=[],
                    parser_used=ParserType.DOCLING,
                    metadata={
                        "source": "docling",
                        "note": "Validation failed; returned text-only content",
                        "validation_error": str(ve),
                    },
                )

            return pdf_content

        except PDFValidationError as e:
            error_msg = str(e).lower()
            if "too large" in error_msg or "too many pages" in error_msg:
                logger.info(f"Skipping PDF processing due to size/page limits: {e}")
                return None
            else: 
                raise
        except Exception as e: 
            logger.error(f"Failed to parse PDF with Docling: {e}")
            logger.error(f"PDF path: {pdf_path}")
            logger.error(f"PDF size: {pdf_path.stat().st_size} bytes")
            logger.error(f"Error type: {type(e).__name__}")

            # Add specific handling for common issues
            error_msg = str(e).lower()

            if "not valid" in error_msg:
                logger.error("PDF appears to be corrupted or not a valid PDF file")
                raise PDFParsingException(f"PDF appears to be corrupted or invalid: {pdf_path}")
            elif "timeout" in error_msg:
                logger.error("PDF processing timed out - file may be too complex")
                raise PDFParsingException(f"PDF processing timed out: {pdf_path}")
            elif "memory" in error_msg or "ram" in error_msg:
                logger.error("Out of memory - PDF may be too large or complex")
                raise PDFParsingException(f"Out of memory processing PDF: {pdf_path}")
            elif "max_num_pages" in error_msg or "page" in error_msg:
                logger.error(f"PDF processing issue likely related to page limits (current limit: {self.max_pages} pages)")
                raise PDFParsingException(
                    f"PDF processing failed, possibly due to page limit ({self.max_pages} pages). Error: {e}"
                )
            else:
                raise PDFParsingException(f"Failed to parse PDF with Docling: {e}")


            

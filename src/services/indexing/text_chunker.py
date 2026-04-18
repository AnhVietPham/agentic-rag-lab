import json
import logging
import re
from typing import Dict, List, Optional, Union

from src.schemas.indexing.models import TextChunk, ChunkMetadata

logger = logging.getLogger(__name__)

class TextChunker: 
    def __init__(
        self, 
        chunk_size: int = 600, 
        overlap_size: int = 100, 
        min_chunk_size: int = 100, 
        ):
        self.chunk_size = chunk_size
        self.overlap_size = overlap_size
        self.min_chunk_size = min_chunk_size

        if overlap_size >= chunk_size: 
            raise ValueError("Overlap size must be less than chunk size")

        logger.info(f"Text chunker initialized with chunk_size: {chunk_size}, overlap_size: {overlap_size}, min_chunk_size: {min_chunk_size}")
    
    def _split_into_words(self, text: str) -> List[str]:
        words = re.findall(f"\S+", text)
        return words
    
    def _reconstruct_text(self, words: List[str]) -> str:
        return " ".join(words)

    def chunk_paper(
        self, 
        title: str, 
        abstract: str,
        full_text: str,
        arxiv_id: str,
        paper_id: str,
        sections: Optional[Union[Dict[str, str], str, list]] = None,
        ) -> List[TextChunk]:

        if sections: 
            try: 
                section_chunks = self._chunk_by_sections(title, abstract, arxiv_id, paper_id, sections)
                if section_chunks: 
                    logger.info(f"Created {len(section_chunks)} section-based chunks for {arxiv_id}")
                    return section_chunks
            except Exception as e: 
                logger.error(f"Section-based chunking failed for {arxiv_id}: {e}")
        
        logger.warning(f"Using traditional word-based chunking for {arxiv_id}")
        return self.chunk_text(full_text, arxiv_id, paper_id)
    
    def chunk_text(self, text: str, arxiv_id: str, paper_id: str) -> List[TextChunk]: 
        if not text or not text.strip(): 
            logger.warning(f"Empty text provided for {arxiv_id}")
            return []
        
        words = self._split_into_words(text)

        if len(words) < self.min_chunk_size: 
            logger.warning(f"Text too short {arxiv_id} has only {len(words)} words, less than minimum chunk size of {self.min_chunk_size}")
            if words: 
                return [
                    TextChunk(
                        text=self._reconstruct_text(words),
                        metadata=ChunkMetadata(
                            chunk_index=0, 
                            start_char=0,
                            end_char=len(text),
                            word_count=len(words),
                            overlap_with_previous=0,
                            overlap_with_next=0,
                        ), 
                        arxiv_id=arxiv_id,
                        paper_id=paper_id,
                    )
                ]
            return []
        
        chunks = []
        chunk_index = 0
        current_position = 0

        while current_position < len(words): 
            chunk_start = current_position
            chunk_end = min(current_position + self.chunk_size, len(words))

            # Extract chunk words
            chunk_words = words[chunk_start:chunk_end]
            chunk_text = self._reconstruct_text(chunk_words)

            # Calculate character offsets (approximate)
            start_char = len(" ".join(words[:chunk_start])) if chunk_start > 0 else 0
            end_char = len(" ".join(words[:chunk_end]))

            # Calculate overlaps
            overlap_with_previous = min(self.overlap_size, chunk_start) if chunk_start > 0  else 0
            overlap_with_next = self.overlap_size if chunk_end < len(words) else 0

            # Create chunk
            chunk = TextChunk(
                text=chunk_text,
                metadata=ChunkMetadata(
                    chunk_index=chunk_index, 
                    start_char=start_char,
                    end_char=end_char,
                    word_count=len(chunk_words), 
                    overlap_with_previous=overlap_with_previous,
                    overlap_with_next=overlap_with_next,
                ), 
                arxiv_id=arxiv_id,
                paper_id=paper_id,
            )
            chunks.append(chunk)

            # Move to next chunk position (with overlap)
            current_position += self.chunk_size - self.overlap_size
            chunk_index += 1

            # Break if we've processed all words
            if chunk_end >= len(words): 
                break
        
        logger.info(f"Chunked paper {arxiv_id}: {len(chunks)} words -> {len(chunks)} chunks")

        return chunks

    def _chunk_by_sections(
        self, title: str, abstract: str, arxiv_id: str, paper_id: str, sections: Union[Dict[str, str], str, list]
    ) -> List[TextChunk]:
        """Implement hybrid section-based chunking strategy.

        :param title: Paper title
        :param abstract: Paper abstract
        :param arxiv_id: ArXiv ID
        :param paper_id: Database ID
        :param sections: Sections data
        :returns: List of text chunks
        """
        # Parse sections data
        sections_dict = self._parse_sections(sections)
        if not sections_dict:
            return []

        # Filter and clean sections
        sections_dict = self._filter_sections(sections_dict, abstract)
        if not sections_dict:
            logger.warning(f"No meaningful sections found after filtering for {arxiv_id}")
            return []

        # Create header (title + abstract)
        header = f"{title}\n\nAbstract: {abstract}\n\n"

        # Process sections using hybrid strategy
        chunks = []
        small_sections = []  # Buffer for combining small sections

        section_items = list(sections_dict.items())

        for i, (section_title, section_content) in enumerate(section_items):
            content_str = str(section_content) if section_content else ""
            section_words = len(content_str.split())

            if section_words < 100:
                # Collect small sections to combine later
                small_sections.append((section_title, content_str, section_words))

                # If this is the last section or next section is large, process accumulated small sections
                if i == len(section_items) - 1 or len(str(section_items[i + 1][1]).split()) >= 100:
                    chunks.extend(self._create_combined_chunk(header, small_sections, chunks, arxiv_id, paper_id))
                    small_sections = []

            elif 100 <= section_words <= 800:
                # Perfect size - create single chunk
                chunk_text = f"{header}Section: {section_title}\n\n{content_str}"
                chunk = self._create_section_chunk(chunk_text, section_title, len(chunks), arxiv_id, paper_id)
                chunks.append(chunk)

            else:
                # Large section - split using traditional chunking
                section_text = f"Section: {section_title}\n\n{content_str}"
                full_section_text = f"{header}{section_text}"

                # Use traditional chunking but with section context
                section_chunks = self._split_large_section(
                    full_section_text, header, section_title, len(chunks), arxiv_id, paper_id
                )
                chunks.extend(section_chunks)

        return chunks

    def _parse_sections(self, sections: Union[Dict[str, str], str, list]) -> Dict[str, str]: 
        if isinstance(sections, dict): 
            return sections
        elif isinstance(sections, list):
            result = {}
            for i, section in enumerate(sections): 
                if isinstance(section, dict): 
                    title = section.get("title", section.get("heading", f"Section {i+1}")) 
                    content = section.get("content", section.get("text", ""))
                    result[title] = content
                else: 
                    result[f"Section {i + 1}"] = str(section)
            return result
        elif isinstance(sections, str): 
            try: 
                parsed = json.loads(sections)
                if isinstance(parsed, dict): 
                    return parsed
                elif isinstance(parsed, list): 
                    result = {}
                    for i, section in enumerate(parsed): 
                        if isinstance(section, dict): 
                            title = section.get("title", section.get("heading", f"Section {i+1}")) 
                            content = section.get("content", section.get("text", ""))
                            result[title] = content
                        else: 
                            result[f"Section {i + 1}"] = str(section)
                    return result
            except json.JSONDecodeError: 
                logger.warning(f"Invalid JSON format for sections: {sections}")
        return {}

    def _filter_sections(
        self,
        sections_dict: Dict[str, str],
        abstract: str
    ) -> Dict[str, str]:
        filtered = {}
        abstract_words = set(abstract.lower().split())

        for section_title, section_content in sections_dict.items(): 
            content_str = str(section_content).strip()

            if not content_str: 
                continue
                
            if self._is_metadata_section(section_title): 
                continue
                
            if self._is_duplicate_section(content_str, abstract_words): 
                logger.debug(f"Skipping duplicate section: {section_title}")
                continue
            
            # Skip sections that are too smart and contain only metadata
            if len(content_str.split()) < 20 and self._is_metadata_content(content_str): 
                logger.debug(f"Skipping metadata-only section: {section_title}")
                continue

            filtered[section_title] = content_str
        return filtered
    
    def _is_metadata_section(self, section_title: str) -> bool: 
        title_lower = section_title.lower().strip()

        metadata_indicators = [
            "content", 
            "header", 
            "authors", 
            "affiliations", 
            "email", 
            "arxiv", 
            "preprint", 
            "submitted", 
            "received", 
            "accepted"
        ]

        if title_lower in metadata_indicators or len(title_lower) < 5:
            return True
        
        for indicator in metadata_indicators: 
            if indicator in title_lower and len(title_lower) < 20:
                return True
        
        return False

    def _is_duplicate_section(self, content: str, abstract_words: set) -> bool:
        content_lower = content.lower().strip()
        content_words = set(content_lower.split())

        if len(abstract_words) > 10:
            overlap = len(abstract_words.intersection(content_words))
            overlap_ratio = overlap / len(abstract_words)

            if overlap_ratio > 0.5:
                return True
        return False

    def _is_metadata_content(self, content: str) -> bool:
        content_lower = content.lower()

        metadata_patterns = [
            "@",  # Email addresses
            "arxiv:",  # ArXiv IDs
            "university",
            "institute",
            "department",
            "college",
            "gmail.com",
            "edu",
            "ac.uk",
            "preprint",
        ]

        word_count = len(content.split())
        if word_count < 30: 
            metadata_word_count = sum(1 for pattern in metadata_patterns if pattern in content_lower)
            if metadata_word_count >= 2: 
                return True
        return False
    
    def _create_combined_chunk(
        self,
        header: str, 
        small_sections: List,
        existing_chunks: List, 
        arxiv_id: str,
        paper_id: str
    ) -> List[TextChunk]:
        if not small_sections: 
            return []

        combined_content = []
        total_words = 0

        for section_title, content, word_count in small_sections:
            combined_content.append(f"Section: {section_title}\n\n{content}")
            total_words += word_count
        
        combined_text = f"{header}{'\\n\\n'.join(combined_content)}"

        if total_words + len(header.split()) < 200 and existing_chunks:
            prev_chunk = existing_chunks[-1]
            merged_text = f"{prev_chunk.text}\\n\\n{'\\n\\n'.join(combined_content)}"

            existing_chunks[-1] = TextChunk(
                text=merged_text,
                metadata=ChunkMetadata(
                    chunk_index=prev_chunk.metadata.chunk_index,
                    start_char=0, 
                    end_char=len(merged_text),
                    word_count=len(merged_text.split()),
                    overlap_with_previous=0,
                    overlap_with_next=0,
                    section_title=f"{prev_chunk.metadata.section_title} + Combined"
                ), 
                arxiv_id=arxiv_id,
                paper_id=paper_id,
            )
            return []

        # Create new chunk with combined content
        sections_titles = [title for title, _, _ in small_sections]
        combined_title =  " + ".join(sections_titles[:3])
        if len(sections_titles) > 3: 
            combined_title += f" + {len(sections_titles) - 3} more"
        
        chunk = self._create_section_chunk(combined_text, combined_title, len(existing_chunks), arxiv_id, paper_id)
        return [chunk]
    
    def _create_section_chunk(
        self, 
        chunk_text: str, 
        section_title: str, 
        chunk_index: int, 
        arxiv_id: str,
        paper_id: str
    ) -> TextChunk: 
        return TextChunk(
            text=chunk_text, 
            metadata=ChunkMetadata(
                chunk_index=chunk_index,
                start_char=0,
                end_char=len(chunk_text),
                word_count=len(chunk_text.split()),
                overlap_with_previous=0,
                overlap_with_next=0,
                section_title=section_title
            ), 
            arxiv_id=arxiv_id,
            paper_id=paper_id,
        )
    
    def _split_large_section(
        self, 
        full_section_text: str, 
        header: str, 
        section_title: str, 
        base_chunk_index: int, 
        arxiv_id: str,
        paper_id: str
    ) -> List[TextChunk]: 
        section_only = full_section_text[len(header) :]

        traditional_chunks = self.chunk_text(section_only, arxiv_id, paper_id)

        enhanced_chunks = []
        for i, chunk in enumerate(traditional_chunks): 
            enhanced_text = f"{header}{chunk.text}"

            enhanced_chunk = TextChunk(
                text=enhanced_text,
                metadata=ChunkMetadata(
                    chunk_index=base_chunk_index + i,
                    start_char=chunk.metadata.start_char,
                    end_char=chunk.metadata.end_char + len(header),
                    word_count = len(enhanced_text.split()),
                    overlap_with_previous=chunk.metadata.overlap_with_previous,
                    overlap_with_next=chunk.metadata.overlap_with_next, 
                    section_title=f"{section_title} (Part {i + 1})"
                ), 
                arxiv_id=arxiv_id,
                paper_id=paper_id,
            )
            enhanced_chunks.append(enhanced_chunk)
        return enhanced_chunks


        


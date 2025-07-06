"""
Enhanced Text Splitter with Markdown-aware features inspired by LlamaIndex MarkdownNodeParser.

Combines the best of LlamaIndex's header-based splitting with our custom data structures
and PostgreSQL backend integration.
"""

import re
from dataclasses import dataclass
from typing import List, Tuple

from .data_structures import Document, TextChunk


@dataclass
class MarkdownTextSplitter:
    """
    Enhanced text splitter with markdown header awareness.

    Inspired by LlamaIndex MarkdownNodeParser but using our custom data structures.
    Features:
    - Header-based hierarchical splitting
    - Code block detection and protection
    - Header path metadata generation
    - Configurable chunk size with fallback splitting
    - PostgreSQL backend integration
    """

    # Header-based splitting configuration
    header_path_separator: str = "/"
    include_header_path: bool = True

    # Fallback text splitting configuration
    chunk_size: int = 512
    chunk_overlap: int = 128
    sentence_separator: str = ". "
    paragraph_separator: str = "\n\n"

    # Advanced features
    protect_code_blocks: bool = True
    min_chunk_size: int = 50  # Don't create chunks smaller than this
    max_chunk_size: int = 2048  # Split large sections if they exceed this

    def split_text_by_headers(self, text: str) -> List[Tuple[str, List[Tuple[int, str]]]]:
        """
        Split text by markdown headers, preserving hierarchy.

        Returns:
            List of (section_text, header_stack) tuples
        """
        sections = []
        lines = text.split("\n")
        current_section_lines = []
        header_stack: List[Tuple[int, str]] = []  # (level, text)
        code_block = False

        for line in lines:
            # Track code block state to protect headers inside code
            if self.protect_code_blocks and line.lstrip().startswith("```"):
                code_block = not code_block
                current_section_lines.append(line)
                continue

            # Parse headers only outside code blocks
            if not code_block:
                header_match = re.match(r"^(#+)\s+(.*)", line)
                if header_match:
                    # Save previous section before starting new one
                    if current_section_lines:
                        section_text = "\n".join(current_section_lines).strip()
                        if len(section_text) >= self.min_chunk_size:
                            sections.append((section_text, header_stack.copy()))
                        current_section_lines = []

                    # Update header stack
                    header_level = len(header_match.group(1))
                    header_text = header_match.group(2).strip()

                    # Pop headers of same or lower level (proper hierarchy)
                    while header_stack and header_stack[-1][0] >= header_level:
                        header_stack.pop()

                    # Add new header to stack
                    header_stack.append((header_level, header_text))

                    # Include header in the section
                    current_section_lines = [line]
                    continue

            current_section_lines.append(line)

        # Add final section
        if current_section_lines:
            section_text = "\n".join(current_section_lines).strip()
            if len(section_text) >= self.min_chunk_size:
                sections.append((section_text, header_stack.copy()))

        return sections

    def split_large_section(self, text: str) -> List[str]:
        """
        Split a large section that exceeds max_chunk_size using sentence boundaries.
        Fallback to our original text splitting logic.
        """
        if len(text) <= self.max_chunk_size:
            return [text]

        # Try splitting by paragraphs first
        paragraphs = text.split(self.paragraph_separator)
        chunks = []
        current_chunk = ""

        for paragraph in paragraphs:
            # If single paragraph is too long, split by sentences
            if len(paragraph) > self.chunk_size:
                sentences = paragraph.split(self.sentence_separator)

                for sentence in sentences:
                    sentence = sentence.strip()
                    if not sentence:
                        continue

                    # Add sentence separator back
                    if not sentence.endswith("."):
                        sentence += self.sentence_separator.strip()

                    # Check if adding sentence exceeds chunk size
                    if len(current_chunk) + len(sentence) + 1 > self.chunk_size:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                        current_chunk = sentence
                    else:
                        if current_chunk:
                            current_chunk += " "
                        current_chunk += sentence
            # Add whole paragraph if it fits
            elif len(current_chunk) + len(paragraph) + 2 > self.chunk_size:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = paragraph
            else:
                if current_chunk:
                    current_chunk += self.paragraph_separator
                current_chunk += paragraph

        # Don't forget the last chunk
        if current_chunk:
            chunks.append(current_chunk.strip())

        # Apply overlap between chunks
        if self.chunk_overlap > 0 and len(chunks) > 1:
            overlapped_chunks = []
            for i, chunk in enumerate(chunks):
                if i > 0:
                    # Get overlap from previous chunk
                    prev_chunk = chunks[i - 1]
                    overlap_text = self._get_overlap(prev_chunk, self.chunk_overlap)
                    chunk = overlap_text + " " + chunk
                overlapped_chunks.append(chunk)
            return overlapped_chunks

        return chunks

    def _get_overlap(self, text: str, overlap_size: int) -> str:
        """Get overlap text from the end of a chunk."""
        if len(text) <= overlap_size:
            return text

        # Try to break at word boundary
        overlap_text = text[-overlap_size:]
        space_idx = overlap_text.find(" ")
        if space_idx > 0:
            overlap_text = overlap_text[space_idx + 1 :]

        return overlap_text

    def create_header_path(self, header_stack: List[Tuple[int, str]]) -> str:
        """Create a hierarchical header path from the header stack."""
        if not header_stack:
            return ""

        return self.header_path_separator.join([header[1] for header in header_stack])

    def create_chunks(self, document: Document) -> List[TextChunk]:
        """
        Create TextChunk objects from a Document using markdown-aware splitting.

        This is our main method that replaces the simple TextSplitter.create_chunks()
        with enhanced markdown awareness.
        """
        # First, try header-based splitting
        sections = self.split_text_by_headers(document.text)

        if not sections:
            # Fallback to simple text splitting if no headers found
            return self._create_chunks_simple(document)

        chunks = []
        chunk_index = 0
        current_idx = 0

        for section_text, header_stack in sections:
            # Check if section is too large and needs further splitting
            if len(section_text) > self.max_chunk_size:
                sub_chunks = self.split_large_section(section_text)
            else:
                sub_chunks = [section_text]

            # Create TextChunk objects for each sub-chunk
            for sub_chunk_text in sub_chunks:
                # Create header path metadata
                header_path = (
                    self.create_header_path(header_stack) if self.include_header_path else ""
                )

                # Enhanced metadata with header information
                chunk_metadata = {
                    **document.metadata,
                    "chunk_index": chunk_index,
                    "doc_id": document.doc_id,
                    "header_path": header_path,
                    "header_level": header_stack[-1][0] if header_stack else 0,
                    "current_header": header_stack[-1][1] if header_stack else "",
                    "total_header_levels": len(header_stack),
                    "splitting_method": "header_based" if header_stack else "text_based",
                }

                chunk = TextChunk(
                    text=sub_chunk_text,
                    metadata=chunk_metadata,
                    start_char_idx=current_idx,
                    end_char_idx=current_idx + len(sub_chunk_text),
                    relationships={"source": document.doc_id},
                )

                chunks.append(chunk)
                chunk_index += 1
                current_idx += len(sub_chunk_text) + 1

        return chunks

    def _create_chunks_simple(self, document: Document) -> List[TextChunk]:
        """Fallback to simple text splitting when no headers are found."""
        # Use our original simple splitting logic
        from .data_structures import TextSplitter

        simple_splitter = TextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separator=self.sentence_separator,
            paragraph_separator=self.paragraph_separator,
        )

        return simple_splitter.create_chunks(document)


# Convenience function to maintain compatibility
def create_enhanced_text_splitter(
    config=None, header_aware: bool = True, protect_code_blocks: bool = True, **kwargs
) -> MarkdownTextSplitter:
    """
    Create an enhanced text splitter with sensible defaults.

    Args:
        config: PipelineConfig object (optional)
        header_aware: Enable markdown header-based splitting
        protect_code_blocks: Protect code blocks from header parsing
        **kwargs: Additional arguments for MarkdownTextSplitter
    """
    # Get configuration from config object if provided
    chunk_size = config.chunking.chunk_size if config else 512
    chunk_overlap = config.chunking.chunk_overlap if config else 128

    return MarkdownTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        protect_code_blocks=protect_code_blocks,
        **kwargs,
    )

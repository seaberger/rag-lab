"""
Custom data structures to replace LlamaIndex dependencies.

Simple, lightweight alternatives to LlamaIndex Document and TextNode
that provide exactly what we need without external dependencies.
"""

import hashlib
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple


@dataclass
class Document:
    """
    A document container for text and metadata.
    Replaces llama_index.core.Document with full metadata support.
    """

    text: str
    doc_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    metadata: Dict[str, Any] = field(default_factory=dict)
    excluded_embed_metadata_keys: List[str] = field(default_factory=list)
    excluded_llm_metadata_keys: List[str] = field(default_factory=list)

    # Common metadata fields for type hints and IDE support
    # These are stored in the metadata dict but exposed for convenience
    @property
    def source(self) -> str | None:
        """Get document source path."""
        return self.metadata.get("source")

    @property
    def source_type(self) -> str | None:
        """Get document source type."""
        return self.metadata.get("source_type")

    @property
    def pairs(self) -> List[Tuple[str, str]]:
        """Get model/part number pairs."""
        return self.metadata.get("pairs", [])

    @pairs.setter
    def pairs(self, value: List[Tuple[str, str]]):
        """Set model/part number pairs."""
        self.metadata["pairs"] = value

    @property
    def hash(self) -> str:
        """Generate a hash of the document content."""
        return hashlib.sha256(self.text.encode()).hexdigest()

    def __post_init__(self):
        """Ensure doc_id is in metadata and validate pairs."""
        if self.doc_id and "doc_id" not in self.metadata:
            self.metadata["doc_id"] = self.doc_id

        # Ensure pairs is a list of tuples
        if "pairs" in self.metadata:
            pairs = self.metadata["pairs"]
            if pairs and not isinstance(pairs[0], tuple):
                # Convert list of lists to list of tuples
                self.metadata["pairs"] = [tuple(pair) for pair in pairs]

    def set_metadata(self, key: str, value: Any) -> None:
        """Set a metadata field."""
        self.metadata[key] = value

    def get_metadata(self, key: str, default: Any = None) -> Any:
        """Get a metadata field with optional default."""
        return self.metadata.get(key, default)


@dataclass
class TextChunk:
    """
    A text chunk with metadata.
    Replaces llama_index.core.TextNode with full metadata support.
    """

    text: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    metadata: Dict[str, Any] = field(default_factory=dict)
    start_char_idx: int | None = None
    end_char_idx: int | None = None
    relationships: Dict[str, Any] = field(default_factory=dict)
    embedding: List[float] | None = None
    excluded_embed_metadata_keys: List[str] = field(default_factory=list)
    excluded_llm_metadata_keys: List[str] = field(default_factory=list)

    # Aliases for LlamaIndex compatibility
    @property
    def node_id(self) -> str:
        """Alias for compatibility."""
        return self.id

    @property
    def id_(self) -> str:
        """LlamaIndex compatibility alias."""
        return self.id

    # Common metadata accessors
    @property
    def doc_id(self) -> str | None:
        """Get parent document ID."""
        return self.metadata.get("doc_id")

    @property
    def chunk_index(self) -> int | None:
        """Get chunk index in document."""
        return self.metadata.get("chunk_index")

    @property
    def source(self) -> str | None:
        """Get document source."""
        return self.metadata.get("source")

    @property
    def pairs(self) -> List[Tuple[str, str]]:
        """Get model/part number pairs from parent document."""
        pairs = self.metadata.get("pairs", [])
        # Ensure they're tuples
        if pairs and not isinstance(pairs[0], tuple):
            return [tuple(pair) for pair in pairs]
        return pairs

    @property
    def keywords(self) -> List[str]:
        """Get extracted keywords for this chunk."""
        return self.metadata.get("keywords", [])

    @property
    def hash(self) -> str:
        """Generate a hash of the chunk content."""
        return hashlib.sha256(self.text.encode()).hexdigest()

    @property
    def content_hash(self) -> str:
        """Alias for hash (compatibility)."""
        return self.hash

    def get_content(self, metadata_mode: bool = False) -> str:
        """Get chunk content, optionally with metadata."""
        if metadata_mode and self.metadata:
            # Filter out excluded keys
            included_meta = {
                k: v for k, v in self.metadata.items() if k not in self.excluded_llm_metadata_keys
            }
            if included_meta:
                metadata_str = "\n".join(f"{k}: {v}" for k, v in included_meta.items())
                return f"{metadata_str}\n\n{self.text}"
        return self.text

    def get_metadata_str(self, keys: List[str] | None = None) -> str:
        """Get metadata as formatted string."""
        if not self.metadata:
            return ""

        meta_dict = self.metadata
        if keys:
            meta_dict = {k: v for k, v in self.metadata.items() if k in keys}

        # Exclude specified keys
        meta_dict = {k: v for k, v in meta_dict.items() if k not in self.excluded_llm_metadata_keys}

        return "\n".join(f"{k}: {v}" for k, v in meta_dict.items())

    def __post_init__(self):
        """Ensure metadata consistency."""
        # Store content hash in metadata if not present
        if "content_hash" not in self.metadata:
            self.metadata["content_hash"] = self.hash

        # Ensure pairs is list of tuples if present
        if "pairs" in self.metadata:
            pairs = self.metadata["pairs"]
            if pairs and not isinstance(pairs[0], tuple):
                self.metadata["pairs"] = [tuple(pair) for pair in pairs]


@dataclass
class ChunkWithScore:
    """
    A chunk with relevance score.
    Replaces NodeWithScore from LlamaIndex.
    """

    chunk: TextChunk
    score: float

    @property
    def node(self):
        """Alias for compatibility."""
        return self.chunk

    @property
    def text(self) -> str:
        """Direct access to text."""
        return self.chunk.text

    @property
    def metadata(self) -> Dict[str, Any]:
        """Direct access to metadata."""
        return self.chunk.metadata


@dataclass
class QueryBundle:
    """
    A query with optional embedding.
    Replaces QueryBundle from LlamaIndex.
    """

    query_str: str
    embedding: List[float] | None = None

    @property
    def query(self) -> str:
        """Alias for compatibility."""
        return self.query_str


class TextSplitter:
    """
    Simple text splitter to replace SentenceSplitter.
    Uses sentence boundaries with configurable chunk size and overlap.
    """

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 128,
        separator: str = ". ",
        paragraph_separator: str = "\n\n",
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separator = separator
        self.paragraph_separator = paragraph_separator

    def split_text(self, text: str) -> List[str]:
        """Split text into chunks."""
        # First split by paragraphs
        paragraphs = text.split(self.paragraph_separator)

        chunks = []
        current_chunk = ""

        for paragraph in paragraphs:
            # If paragraph is too long, split by sentences
            if len(paragraph) > self.chunk_size:
                sentences = paragraph.split(self.separator)

                for sentence in sentences:
                    sentence = sentence.strip()
                    if not sentence:
                        continue

                    # Add sentence separator back
                    if not sentence.endswith("."):
                        sentence += self.separator.strip()

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

        # Apply overlap
        if self.chunk_overlap > 0 and len(chunks) > 1:
            overlapped_chunks = []
            for i, chunk in enumerate(chunks):
                if i > 0:
                    # Get overlap from previous chunk
                    prev_chunk = chunks[i - 1]
                    overlap_text = self._get_overlap(prev_chunk, self.chunk_overlap)
                    chunk = overlap_text + " " + chunk
                overlapped_chunks.append(chunk)
            chunks = overlapped_chunks

        return chunks

    def _get_overlap(self, text: str, overlap_size: int) -> str:
        """Get the last overlap_size characters from text."""
        if len(text) <= overlap_size:
            return text

        # Try to find a good break point (word boundary)
        overlap_text = text[-overlap_size:]
        first_space = overlap_text.find(" ")
        if first_space > 0:
            overlap_text = overlap_text[first_space + 1 :]

        return overlap_text

    def create_chunks(self, document: Document) -> List[TextChunk]:
        """Create TextChunk objects from a Document."""
        text_splits = self.split_text(document.text)

        chunks = []
        current_idx = 0

        for i, text in enumerate(text_splits):
            chunk = TextChunk(
                text=text,
                metadata={
                    **document.metadata,
                    "chunk_index": i,
                    "doc_id": document.doc_id,
                },
                start_char_idx=current_idx,
                end_char_idx=current_idx + len(text),
                relationships={"source": document.doc_id},
            )
            chunks.append(chunk)
            current_idx += len(text) + 1  # +1 for separator

        return chunks


# Compatibility aliases
TextNode = TextChunk
NodeWithScore = ChunkWithScore


class MetadataBuilder:
    """Helper class for building rich metadata with validation."""

    @staticmethod
    def build_document_metadata(
        source: str,
        source_type: str = "unknown",
        pairs: List[Tuple[str, str]] | None = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Build document metadata with common fields.

        Args:
            source: Document source path or URL
            source_type: Type of document (datasheet_pdf, generic_pdf, etc.)
            pairs: List of (model, part_number) tuples
            **kwargs: Additional metadata fields

        Returns:
            Complete metadata dictionary
        """
        metadata = {
            "source": source,
            "source_type": source_type,
            "file_name": Path(source).name if source else "unknown",
            "pairs": pairs or [],
            "extracted_pairs": len(pairs) if pairs else 0,
        }

        # Add any additional fields
        metadata.update(kwargs)

        # Ensure pairs are tuples
        if metadata["pairs"] and not isinstance(metadata["pairs"][0], tuple):
            metadata["pairs"] = [tuple(pair) for pair in metadata["pairs"]]

        return metadata

    @staticmethod
    def validate_pairs(pairs: List[Any]) -> List[Tuple[str, str]]:
        """
        Validate and normalize model/part number pairs.

        Args:
            pairs: List of pairs in various formats

        Returns:
            Normalized list of tuples
        """
        if not pairs:
            return []

        normalized = []
        for pair in pairs:
            if isinstance(pair, tuple) and len(pair) == 2:
                normalized.append(pair)
            elif isinstance(pair, list) and len(pair) == 2:
                normalized.append(tuple(pair))
            elif isinstance(pair, dict) and "model" in pair and "part" in pair:
                normalized.append((pair["model"], pair["part"]))
            else:
                # Skip invalid pairs
                continue

        return normalized

    @staticmethod
    def merge_metadata(base: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merge metadata dictionaries with special handling for pairs and lists.

        Args:
            base: Base metadata dictionary
            update: Updates to apply

        Returns:
            Merged metadata
        """
        merged = base.copy()

        for key, value in update.items():
            if key == "pairs" and key in merged:
                # Merge pairs lists
                existing = MetadataBuilder.validate_pairs(merged[key])
                new = MetadataBuilder.validate_pairs(value)
                # Combine and deduplicate
                combined = list(dict.fromkeys(existing + new))
                merged[key] = combined
            elif key in merged and isinstance(merged[key], list) and isinstance(value, list):
                # Merge other lists
                merged[key] = list(set(merged[key] + value))
            else:
                # Override for other types
                merged[key] = value

        return merged


# Markdown splitter using simple regex
class MarkdownSplitter(TextSplitter):
    """
    Markdown-aware text splitter that preserves structure.
    Replaces MarkdownNodeParser from LlamaIndex.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.header_pattern = r"^(#{1,6})\s+(.+)$"

    def split_text(self, text: str) -> List[str]:
        """Split markdown text while preserving headers."""
        import re

        # Split by headers first
        lines = text.split("\n")
        sections = []
        current_section = []
        current_header = None

        for line in lines:
            header_match = re.match(self.header_pattern, line)
            if header_match:
                # Save previous section
                if current_section:
                    section_text = "\n".join(current_section)
                    if current_header:
                        section_text = current_header + "\n" + section_text
                    sections.append(section_text)

                # Start new section
                current_header = line
                current_section = []
            else:
                current_section.append(line)

        # Don't forget the last section
        if current_section:
            section_text = "\n".join(current_section)
            if current_header:
                section_text = current_header + "\n" + section_text
            sections.append(section_text)

        # Now apply size-based chunking to each section
        chunks = []
        for section in sections:
            if len(section) > self.chunk_size:
                # Use parent's splitting logic
                section_chunks = super().split_text(section)
                chunks.extend(section_chunks)
            else:
                chunks.append(section)

        return chunks

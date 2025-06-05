# The chunking and metadata enhancement remains the same
from contextlib import nullcontext
from typing import Any, Dict, List, Optional, Tuple

from llama_index.core.node_parser import MarkdownNodeParser
from llama_index.core.schema import Document, TextNode

from .monitoring import ProgressMonitor

from openai import OpenAI
from .common_utils import logger, retry_api_call

class KeywordGenerator:
    """Generate contextual keywords for document chunks using OpenAI."""
    
    def __init__(self, model: str = "gpt-4o-mini", max_keywords: int = 10):
        self.client = OpenAI()
        self.model = model
        self.max_keywords = max_keywords
    
    async def atransform(self, nodes: List[TextNode]) -> List[TextNode]:
        """Transform nodes by appending keywords to content (per Anthropic RAG best practices)."""
        try:
            # Process nodes individually for better context
            for node in nodes:
                keywords = await self._generate_keywords_for_node(node)
                if keywords:
                    # Append keywords to content as a block (Anthropic RAG best practice)
                    keyword_block = "\n\n---\nKeywords: " + ", ".join(keywords)
                    node.text = node.text + keyword_block
                    # Also keep in metadata for reference
                    node.metadata["keywords"] = keywords
                
            logger.info(f"Added keywords to {len(nodes)} nodes")
            return nodes
        except Exception as e:
            logger.error(f"Keyword generation failed: {e}")
            return nodes  # Return original nodes on failure
    
    async def _generate_keywords_for_node(self, node: TextNode) -> List[str]:
        """Generate keywords for a single node."""
        
        # Create keyword generation prompt
        prompt = f"""Extract {self.max_keywords} relevant keywords and phrases from this technical document chunk.

Focus on:
- Technical terms and specifications
- Product names and model numbers  
- Part numbers and identifiers
- Measurement units and ranges
- Key features and capabilities

Text chunk:
{node.text[:1000]}...

Return only a JSON list of keywords, like: ["keyword1", "keyword2", ...]"""

        @retry_api_call(max_attempts=3)
        async def call_api():
            return self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=200
            )
        
        try:
            response = await call_api()
            keywords_text = response.choices[0].message.content.strip()
            
            # Parse JSON response
            import json
            # Handle single quotes in the response by converting to double quotes
            keywords_text = keywords_text.replace("'", '"')
            keywords = json.loads(keywords_text)
            if isinstance(keywords, list):
                return [str(k).strip() for k in keywords if k]
            else:
                logger.warning(f"Unexpected keyword format: {keywords_text}")
                return []
                
        except Exception as e:
            logger.warning(f"Failed to generate keywords for node: {e}")
            return []

async def batch_generate_keywords(
    nodes: List[TextNode], 
    model: str = "gpt-4o-mini",
    batch_size: int = 10
) -> List[TextNode]:
    """Generate keywords for multiple nodes in batches for cost efficiency."""
    
    if not nodes:
        return nodes
        
    logger.info(f"Starting batch keyword generation for {len(nodes)} nodes")
    
    # Create batches of nodes
    batches = [nodes[i:i + batch_size] for i in range(0, len(nodes), batch_size)]
    
    for batch_idx, batch in enumerate(batches):
        try:
            # Create combined prompt for batch
            batch_text = ""
            for i, node in enumerate(batch):
                batch_text += f"\n--- Document Chunk {i+1} ---\n{node.text[:500]}...\n"
            
            prompt = f"""Generate keywords for each of these {len(batch)} technical document chunks.

For each chunk, extract 5-8 relevant keywords focusing on:
- Technical terms and specifications
- Product names and model numbers
- Part numbers and identifiers  
- Measurement units and ranges
- Key features and capabilities

Text chunks:
{batch_text}

Return JSON format:
{{
    "chunk_1": ["keyword1", "keyword2", ...],
    "chunk_2": ["keyword1", "keyword2", ...],
    ...
}}"""

            @retry_api_call(max_attempts=3)
            async def call_batch_api():
                client = OpenAI()
                return client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=800
                )
            
            response = await call_batch_api()
            result_text = response.choices[0].message.content.strip()
            
            # Parse batch results
            import json
            # Handle single quotes in the response by converting to double quotes
            result_text = result_text.replace("'", '"')
            batch_keywords = json.loads(result_text)
            
            # Apply keywords to nodes
            for i, node in enumerate(batch):
                chunk_key = f"chunk_{i+1}"
                if chunk_key in batch_keywords:
                    keywords = batch_keywords[chunk_key]
                    if isinstance(keywords, list):
                        keywords = [str(k).strip() for k in keywords if k]
                        if keywords:
                            # Append keywords to content as a block (Anthropic RAG best practice)
                            keyword_block = "\n\n---\nKeywords: " + ", ".join(keywords)
                            node.text = node.text + keyword_block
                            # Also keep in metadata for reference
                            node.metadata["keywords"] = keywords
                        else:
                            node.metadata["keywords"] = []
                    else:
                        node.metadata["keywords"] = []
                else:
                    node.metadata["keywords"] = []
                    
            logger.info(f"Processed batch {batch_idx + 1}/{len(batches)}")
            
        except Exception as e:
            logger.error(f"Batch {batch_idx + 1} keyword generation failed: {e}")
            # Set empty keywords for failed batch
            for node in batch:
                node.metadata["keywords"] = []
    
    logger.info(f"Completed batch keyword generation for {len(nodes)} nodes")
    return nodes


async def process_and_index_document(
    doc_id: str,
    source: str,
    markdown: str,
    pairs: List[Tuple[str, str]],
    metadata: Dict[str, Any],
    with_keywords: bool = False,
    progress: Optional[ProgressMonitor] = None,
    config = None,  # PipelineConfig
) -> List[TextNode]:
    """Chunk document and add metadata + optional keywords."""

    # Create document with metadata
    doc = Document(
        text=markdown,
        metadata={
            "doc_id": doc_id,
            "source": source,
            "pairs": pairs,  # Model/part number pairs
            **metadata,  # Additional metadata from parsing
        },
    )

    # Chunk using MarkdownNodeParser (preserves structure)
    if progress:
        progress.update_stage(doc_id, "chunking")
    md_parser = MarkdownNodeParser()
    nodes = md_parser.get_nodes_from_documents([doc])

    # Add metadata to each chunk
    for node in nodes:
        node.metadata.update(
            {
                "doc_id": doc_id,
                "pairs": pairs,
                "chunk_index": nodes.index(node),
                "total_chunks": len(nodes),
            }
        )

    # Optional keyword augmentation
    if with_keywords:
        if progress:
            progress.update_stage(doc_id, "keywords")
        # Get model from config or use default
        keyword_model = config.openai.keyword_model if config else "gpt-4o-mini"
        batch_threshold = config.batch.threshold if config else 10
        
        if len(nodes) > batch_threshold:  # Use batch for large documents
            nodes = await batch_generate_keywords(nodes, model=keyword_model)
        else:
            keyword_gen = KeywordGenerator(model=keyword_model)
            nodes = await keyword_gen.atransform(nodes)

    return nodes

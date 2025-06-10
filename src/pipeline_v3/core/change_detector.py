"""
Change Detector - Phase 2 Implementation

Intelligent document change detection and update optimization.
Determines optimal update strategies based on content analysis and change patterns.
"""

import hashlib
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

# Add parent directory to path for imports
import sys
sys.path.append(str(Path(__file__).parent.parent))

from core.fingerprint import FingerprintManager, DocumentFingerprint
from core.registry import DocumentRegistry, DocumentState, IndexType
from utils.common_utils import logger
from utils.config import PipelineConfig


class ChangeType(Enum):
    """Types of document changes."""
    NO_CHANGE = "no_change"
    MINOR_UPDATE = "minor_update"     # Small content changes
    MAJOR_UPDATE = "major_update"     # Significant content changes
    STRUCTURE_CHANGE = "structure_change"  # Document structure changed
    COMPLETE_REWRITE = "complete_rewrite"  # Document completely different
    NEW_DOCUMENT = "new_document"     # Never seen before
    DELETED = "deleted"               # Document no longer exists


class UpdateStrategy(Enum):
    """Update strategies based on change type."""
    SKIP = "skip"                     # No update needed
    INCREMENTAL = "incremental"       # Update only changed chunks
    FULL_REINDEX = "full_reindex"     # Complete reindexing required
    REMOVE = "remove"                 # Remove from indexes


@dataclass
class ChangeAnalysis:
    """Analysis of document changes."""
    doc_id: str
    source: str
    change_type: ChangeType
    update_strategy: UpdateStrategy
    confidence: float
    old_fingerprint: Optional[DocumentFingerprint]
    new_fingerprint: Optional[DocumentFingerprint]
    change_summary: Dict[str, Any]
    affected_chunks: List[int]
    processing_priority: int  # 1=urgent, 2=normal, 3=low
    estimated_effort: float   # Processing time estimate in seconds


@dataclass
class ChunkComparison:
    """Comparison result for document chunks."""
    chunk_index: int
    old_hash: Optional[str]
    new_hash: Optional[str]
    similarity_score: float
    change_type: str  # added, removed, modified, unchanged
    content_sample: str


class ChangeDetector:
    """Intelligent document change detection and update optimization."""
    
    def __init__(self, config: Optional[PipelineConfig] = None, registry: Optional[DocumentRegistry] = None):
        """Initialize change detector with configuration."""
        self.config = config or PipelineConfig()
        
        # Initialize components
        self.fingerprint_manager = FingerprintManager(config)
        self.registry = registry or DocumentRegistry(config)
        
        # Configuration thresholds
        self.minor_change_threshold = 0.15      # 15% content change
        self.major_change_threshold = 0.40      # 40% content change
        self.structure_change_threshold = 0.70  # 70% structure change
        self.rewrite_threshold = 0.90           # 90% different content
        
        # Chunk similarity thresholds
        self.chunk_similarity_threshold = 0.80  # 80% similarity for unchanged
        self.chunk_modification_threshold = 0.50  # 50% similarity for modification
        
        logger.info("ChangeDetector initialized with intelligent update strategies")
    
    def analyze_changes(
        self,
        source: Union[str, Path],
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ChangeAnalysis:
        """Analyze document changes and determine update strategy."""
        try:
            source_path = Path(source)
            
            # Get current fingerprint
            current_fingerprint = self.fingerprint_manager.compute_fingerprint(
                source, include_metadata=True
            )
            
            # Get stored fingerprint and registry record
            stored_fingerprint = self.fingerprint_manager.get_fingerprint(source)
            registry_doc = self.registry.get_document_by_source(source)
            
            # Determine change type
            change_type = self._determine_change_type(
                current_fingerprint, stored_fingerprint, registry_doc
            )
            
            # Analyze content changes if document exists
            change_summary = {}
            affected_chunks = []
            confidence = 1.0
            
            if stored_fingerprint and change_type != ChangeType.NEW_DOCUMENT:
                # Perform detailed content analysis
                content_analysis = self._analyze_content_changes(
                    source, content, registry_doc
                )
                change_summary = content_analysis["summary"]
                affected_chunks = content_analysis["affected_chunks"]
                confidence = content_analysis["confidence"]
                
                # Refine change type based on content analysis
                change_type = self._refine_change_type(change_type, content_analysis)
            
            # Determine update strategy
            update_strategy = self._determine_update_strategy(change_type, change_summary)
            
            # Calculate processing priority
            priority = self._calculate_priority(change_type, change_summary)
            
            # Estimate processing effort
            effort = self._estimate_effort(change_type, content, affected_chunks)
            
            return ChangeAnalysis(
                doc_id=registry_doc.doc_id if registry_doc else "",
                source=str(source_path.resolve()),
                change_type=change_type,
                update_strategy=update_strategy,
                confidence=confidence,
                old_fingerprint=stored_fingerprint,
                new_fingerprint=current_fingerprint,
                change_summary=change_summary,
                affected_chunks=affected_chunks,
                processing_priority=priority,
                estimated_effort=effort
            )
            
        except Exception as e:
            logger.error(f"Change analysis failed for {source}: {e}")
            
            # Return safe fallback analysis
            return ChangeAnalysis(
                doc_id="",
                source=str(source),
                change_type=ChangeType.COMPLETE_REWRITE,
                update_strategy=UpdateStrategy.FULL_REINDEX,
                confidence=0.0,
                old_fingerprint=None,
                new_fingerprint=None,
                change_summary={"error": str(e)},
                affected_chunks=[],
                processing_priority=1,
                estimated_effort=60.0
            )
    
    def _determine_change_type(
        self,
        current: DocumentFingerprint,
        stored: Optional[DocumentFingerprint],
        registry_doc: Optional[Any]
    ) -> ChangeType:
        """Determine the type of change based on fingerprints."""
        if not stored:
            return ChangeType.NEW_DOCUMENT
        
        # Check if file was deleted (this would be handled at a higher level)
        if not Path(current.source).exists():
            return ChangeType.DELETED
        
        # Compare fingerprints
        if current.metadata_hash == stored.metadata_hash:
            return ChangeType.NO_CHANGE
        
        # Check file size change
        size_change_ratio = abs(current.size - stored.size) / max(stored.size, 1)
        
        # Check modification time
        time_diff = current.modified_time - stored.modified_time
        
        # Initial classification based on size and time
        if size_change_ratio > self.rewrite_threshold:
            return ChangeType.COMPLETE_REWRITE
        elif size_change_ratio > self.structure_change_threshold:
            return ChangeType.STRUCTURE_CHANGE
        elif size_change_ratio > self.major_change_threshold:
            return ChangeType.MAJOR_UPDATE
        elif size_change_ratio > self.minor_change_threshold:
            return ChangeType.MINOR_UPDATE
        else:
            # Content changed but size similar - need content analysis
            return ChangeType.MINOR_UPDATE
    
    def _analyze_content_changes(
        self,
        source: Union[str, Path],
        new_content: str,
        registry_doc: Optional[Any]
    ) -> Dict[str, Any]:
        """Perform detailed content analysis to understand changes."""
        try:
            # Get existing chunks from registry/indexes
            old_chunks = []
            if registry_doc:
                # This would need integration with IndexManager to get actual content
                # For now, we'll simulate chunk analysis
                old_chunks = self._simulate_old_chunks(registry_doc)
            
            # Split new content into chunks (simplified)
            new_chunks = self._split_content_into_chunks(new_content)
            
            # Compare chunks
            chunk_comparisons = self._compare_chunks(old_chunks, new_chunks)
            
            # Analyze changes
            total_chunks = max(len(old_chunks), len(new_chunks))
            changed_chunks = sum(1 for comp in chunk_comparisons if comp.change_type != "unchanged")
            
            change_ratio = changed_chunks / max(total_chunks, 1)
            
            # Calculate confidence based on analysis depth
            confidence = min(1.0, 0.7 + (0.3 * min(total_chunks / 10, 1.0)))
            
            # Extract affected chunk indices
            affected_chunks = [
                comp.chunk_index for comp in chunk_comparisons 
                if comp.change_type in ["added", "removed", "modified"]
            ]
            
            return {
                "summary": {
                    "total_old_chunks": len(old_chunks),
                    "total_new_chunks": len(new_chunks),
                    "changed_chunks": changed_chunks,
                    "change_ratio": change_ratio,
                    "chunk_comparisons": len(chunk_comparisons)
                },
                "affected_chunks": affected_chunks,
                "confidence": confidence,
                "chunk_details": [
                    {
                        "index": comp.chunk_index,
                        "change_type": comp.change_type,
                        "similarity": comp.similarity_score
                    }
                    for comp in chunk_comparisons[:10]  # Limit for performance
                ]
            }
            
        except Exception as e:
            logger.error(f"Content analysis failed: {e}")
            return {
                "summary": {"error": str(e)},
                "affected_chunks": [],
                "confidence": 0.0,
                "chunk_details": []
            }
    
    def _simulate_old_chunks(self, registry_doc: Any) -> List[str]:
        """Simulate getting old chunks (would integrate with IndexManager)."""
        # This is a placeholder - in real implementation, would get from IndexManager
        return [f"Old chunk {i}" for i in range(registry_doc.chunk_count)]
    
    def _split_content_into_chunks(self, content: str) -> List[str]:
        """Split content into chunks for comparison."""
        # Simplified chunking - in real implementation, would use proper text splitter
        chunk_size = self.config.chunking.chunk_size
        chunks = []
        
        for i in range(0, len(content), chunk_size):
            chunk = content[i:i + chunk_size]
            chunks.append(chunk)
        
        return chunks
    
    def _compare_chunks(self, old_chunks: List[str], new_chunks: List[str]) -> List[ChunkComparison]:
        """Compare old and new chunks to identify changes."""
        comparisons = []
        
        # Simple comparison algorithm
        max_chunks = max(len(old_chunks), len(new_chunks))
        
        for i in range(max_chunks):
            old_chunk = old_chunks[i] if i < len(old_chunks) else None
            new_chunk = new_chunks[i] if i < len(new_chunks) else None
            
            if old_chunk is None:
                # New chunk added
                comparisons.append(ChunkComparison(
                    chunk_index=i,
                    old_hash=None,
                    new_hash=self._hash_text(new_chunk),
                    similarity_score=0.0,
                    change_type="added",
                    content_sample=new_chunk[:100] if new_chunk else ""
                ))
            elif new_chunk is None:
                # Old chunk removed
                comparisons.append(ChunkComparison(
                    chunk_index=i,
                    old_hash=self._hash_text(old_chunk),
                    new_hash=None,
                    similarity_score=0.0,
                    change_type="removed",
                    content_sample=old_chunk[:100]
                ))
            else:
                # Compare existing chunks
                similarity = self._calculate_text_similarity(old_chunk, new_chunk)
                
                if similarity >= self.chunk_similarity_threshold:
                    change_type = "unchanged"
                elif similarity >= self.chunk_modification_threshold:
                    change_type = "modified"
                else:
                    change_type = "replaced"
                
                comparisons.append(ChunkComparison(
                    chunk_index=i,
                    old_hash=self._hash_text(old_chunk),
                    new_hash=self._hash_text(new_chunk),
                    similarity_score=similarity,
                    change_type=change_type,
                    content_sample=new_chunk[:100]
                ))
        
        return comparisons
    
    def _hash_text(self, text: str) -> str:
        """Generate hash for text content."""
        return hashlib.sha256(text.encode()).hexdigest()[:16]
    
    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two text strings."""
        # Simple similarity based on common words
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 and not words2:
            return 1.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0
    
    def _refine_change_type(
        self, 
        initial_type: ChangeType, 
        content_analysis: Dict[str, Any]
    ) -> ChangeType:
        """Refine change type based on detailed content analysis."""
        if "error" in content_analysis.get("summary", {}):
            return initial_type
        
        summary = content_analysis["summary"]
        change_ratio = summary.get("change_ratio", 0.0)
        
        # Refine based on actual content analysis
        if change_ratio >= self.rewrite_threshold:
            return ChangeType.COMPLETE_REWRITE
        elif change_ratio >= self.structure_change_threshold:
            return ChangeType.STRUCTURE_CHANGE
        elif change_ratio >= self.major_change_threshold:
            return ChangeType.MAJOR_UPDATE
        elif change_ratio >= self.minor_change_threshold:
            return ChangeType.MINOR_UPDATE
        elif change_ratio > 0:
            return ChangeType.MINOR_UPDATE
        else:
            return ChangeType.NO_CHANGE
    
    def _determine_update_strategy(
        self, 
        change_type: ChangeType, 
        change_summary: Dict[str, Any]
    ) -> UpdateStrategy:
        """Determine optimal update strategy based on change type."""
        strategy_map = {
            ChangeType.NO_CHANGE: UpdateStrategy.SKIP,
            ChangeType.MINOR_UPDATE: UpdateStrategy.INCREMENTAL,
            ChangeType.MAJOR_UPDATE: UpdateStrategy.FULL_REINDEX,
            ChangeType.STRUCTURE_CHANGE: UpdateStrategy.FULL_REINDEX,
            ChangeType.COMPLETE_REWRITE: UpdateStrategy.FULL_REINDEX,
            ChangeType.NEW_DOCUMENT: UpdateStrategy.FULL_REINDEX,
            ChangeType.DELETED: UpdateStrategy.REMOVE
        }
        
        base_strategy = strategy_map.get(change_type, UpdateStrategy.FULL_REINDEX)
        
        # Consider incremental updates for minor changes with few affected chunks
        if (change_type == ChangeType.MINOR_UPDATE and 
            change_summary.get("changed_chunks", 0) <= 3):
            return UpdateStrategy.INCREMENTAL
        
        return base_strategy
    
    def _calculate_priority(
        self, 
        change_type: ChangeType, 
        change_summary: Dict[str, Any]
    ) -> int:
        """Calculate processing priority (1=urgent, 2=normal, 3=low)."""
        if change_type in [ChangeType.NEW_DOCUMENT, ChangeType.DELETED]:
            return 1  # Urgent
        elif change_type in [ChangeType.COMPLETE_REWRITE, ChangeType.STRUCTURE_CHANGE]:
            return 1  # Urgent
        elif change_type == ChangeType.MAJOR_UPDATE:
            return 2  # Normal
        elif change_type == ChangeType.MINOR_UPDATE:
            return 2  # Normal
        else:  # NO_CHANGE
            return 3  # Low
    
    def _estimate_effort(
        self, 
        change_type: ChangeType, 
        content: str, 
        affected_chunks: List[int]
    ) -> float:
        """Estimate processing effort in seconds."""
        # Base effort estimates
        base_efforts = {
            ChangeType.NO_CHANGE: 0.1,
            ChangeType.MINOR_UPDATE: 5.0,
            ChangeType.MAJOR_UPDATE: 15.0,
            ChangeType.STRUCTURE_CHANGE: 25.0,
            ChangeType.COMPLETE_REWRITE: 30.0,
            ChangeType.NEW_DOCUMENT: 30.0,
            ChangeType.DELETED: 2.0
        }
        
        base_effort = base_efforts.get(change_type, 30.0)
        
        # Adjust based on content size
        content_factor = min(len(content) / 10000, 3.0)  # Scale with content size
        
        # Adjust based on affected chunks
        chunk_factor = min(len(affected_chunks) / 10, 2.0)
        
        total_effort = base_effort * (1 + content_factor + chunk_factor)
        
        return round(total_effort, 2)
    
    def batch_analyze_changes(
        self, 
        documents: List[Dict[str, Any]]
    ) -> List[ChangeAnalysis]:
        """Analyze changes for multiple documents efficiently."""
        analyses = []
        
        for doc_info in documents:
            try:
                analysis = self.analyze_changes(
                    source=doc_info["source"],
                    content=doc_info["content"],
                    metadata=doc_info.get("metadata")
                )
                analyses.append(analysis)
                
            except Exception as e:
                logger.error(f"Failed to analyze {doc_info.get('source', 'unknown')}: {e}")
                
                # Add error analysis
                analyses.append(ChangeAnalysis(
                    doc_id="",
                    source=doc_info.get("source", "unknown"),
                    change_type=ChangeType.COMPLETE_REWRITE,
                    update_strategy=UpdateStrategy.FULL_REINDEX,
                    confidence=0.0,
                    old_fingerprint=None,
                    new_fingerprint=None,
                    change_summary={"error": str(e)},
                    affected_chunks=[],
                    processing_priority=1,
                    estimated_effort=60.0
                ))
        
        return analyses
    
    def get_update_recommendations(
        self, 
        time_budget: float = 300.0,  # 5 minutes
        max_documents: int = 50
    ) -> Dict[str, Any]:
        """Get prioritized update recommendations based on detected changes."""
        try:
            # Find documents that need updates
            stale_docs = self.registry.list_documents(DocumentState.STALE)
            new_docs = self.registry.list_documents(DocumentState.NEW)
            
            candidates = stale_docs + new_docs
            
            # Analyze changes for candidates
            recommendations = []
            total_effort = 0.0
            
            for doc in candidates[:max_documents]:
                try:
                    # Read document content (simplified)
                    source_path = Path(doc.source)
                    if source_path.exists():
                        content = source_path.read_text(encoding='utf-8', errors='ignore')
                        
                        analysis = self.analyze_changes(doc.source, content)
                        
                        if analysis.update_strategy != UpdateStrategy.SKIP:
                            recommendations.append(analysis)
                            total_effort += analysis.estimated_effort
                            
                            # Stop if we exceed time budget
                            if total_effort > time_budget:
                                break
                        
                except Exception as e:
                    logger.error(f"Failed to analyze {doc.source}: {e}")
            
            # Sort by priority and effort
            recommendations.sort(key=lambda x: (x.processing_priority, x.estimated_effort))
            
            # Fit within time budget
            final_recommendations = []
            budget_used = 0.0
            
            for rec in recommendations:
                if budget_used + rec.estimated_effort <= time_budget:
                    final_recommendations.append(rec)
                    budget_used += rec.estimated_effort
                else:
                    break
            
            return {
                "recommendations": final_recommendations,
                "total_documents": len(final_recommendations),
                "estimated_time": budget_used,
                "time_budget": time_budget,
                "candidates_analyzed": len(candidates),
                "timestamp": time.time()
            }
            
        except Exception as e:
            logger.error(f"Failed to get update recommendations: {e}")
            return {"error": str(e)}
    
    def close(self) -> None:
        """Close detector components."""
        self.fingerprint_manager.close()
        self.registry.close()
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
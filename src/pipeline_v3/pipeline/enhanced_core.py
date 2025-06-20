"""
Enhanced Core Pipeline - Phase 2 Integration

Production-ready document processing pipeline that integrates Phase 1 queue system
with Phase 2 index lifecycle management for intelligent document operations.
"""

import asyncio
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# Add parent directory to path for imports
import sys
sys.path.append(str(Path(__file__).parent.parent))

from core.change_detector import ChangeDetector, ChangeType, UpdateStrategy
from core.fingerprint import FingerprintManager
from core.index_manager import IndexManager, IndexType
from core.pipeline import DatasheetArtefact, DocumentClassifier, fetch_document
from core.parsers import parse_document
from core.registry import DocumentRegistry, DocumentState
from job_queue.manager import DocumentQueue, JobPriority
from job_queue.job import JobManager, JobType, JobStatus
from storage.cache import CacheManager
from utils.common_utils import logger
from utils.config import PipelineConfig
from utils.monitoring import ProgressMonitor


class EnhancedPipeline:
    """Production-ready pipeline with intelligent document lifecycle management."""
    
    def __init__(self, config: Optional[PipelineConfig] = None, registry: Optional[DocumentRegistry] = None, index_manager: Optional[IndexManager] = None):
        """Initialize enhanced pipeline with all components."""
        self.config = config or PipelineConfig()
        
        # Initialize Phase 1 components
        self.document_queue = DocumentQueue(self.config)
        self.job_manager = JobManager(self.config)
        self.fingerprint_manager = FingerprintManager(self.config)
        
        # Initialize Phase 2 components
        self.registry = registry or DocumentRegistry(self.config)
        self.index_manager = index_manager or IndexManager(self.config, registry=self.registry)
        self.change_detector = ChangeDetector(self.config, registry=self.registry)
        
        # Initialize cache for document parsing
        self.cache = CacheManager(config=self.config) if self.config.cache.enabled else None
        
        # Initialize progress monitoring
        self.progress_monitor = ProgressMonitor()
        
        # Processing state
        self.is_processing = False
        self.processing_stats = {
            "documents_processed": 0,
            "documents_added": 0,
            "documents_updated": 0,
            "documents_removed": 0,
            "documents_skipped": 0,
            "processing_errors": 0,
            "start_time": None,
            "total_processing_time": 0.0
        }
        
        logger.info("EnhancedPipeline initialized with full lifecycle management")
    
    def save_processing_report(self, output_file: str = "processing_report_v3.json") -> bool:
        """Save detailed processing report from progress monitor."""
        try:
            return self.progress_monitor.save_report(output_file)
        except Exception as e:
            logger.error(f"Failed to save processing report: {e}")
            return False
    
    async def process_document(
        self,
        source: Union[str, Path],
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        force_reprocess: bool = False,
        index_types: IndexType = IndexType.BOTH,
        mode: str = "auto",
        prompt_file: Optional[str] = None,
        with_keywords: bool = False
    ) -> Dict[str, Any]:
        """Process a single document with intelligent change detection.
        
        Args:
            source: Path to document file or URL
            content: Pre-loaded content (optional)
            metadata: Additional metadata for the document
            force_reprocess: Force reprocessing even if no changes detected
            index_types: Which indexes to update (vector, keyword, or both)
            mode: Document classification mode ('datasheet', 'generic', 'auto')
            prompt_file: Path to custom prompt file for parsing
            with_keywords: Enable keyword generation for enhanced search retrieval
        
        Returns:
            Processing result dictionary with status and details
        """
        start_time = time.time()
        
        # Check if source is a URL
        is_url = str(source).startswith(('http://', 'https://'))
        
        try:
            # Start progress monitoring for this document  
            temp_doc_id = f"temp_{int(time.time()*1000)}"
            self.progress_monitor.start_document(temp_doc_id, str(source))
            
            # Parse document content if not provided
            if content is None:
                self.progress_monitor.update_stage(temp_doc_id, "parsing")
                if not is_url:
                    source_path = Path(source)
                    if not source_path.exists():
                        raise FileNotFoundError(f"Source file not found: {source}")
                
                try:
                    # Parse the document using OpenAI APIs for PDFs
                    content, pairs, parsed_metadata = await self._parse_document_with_openai(
                        source, "temp_id", mode=mode, prompt_file=prompt_file
                    )
                    
                    # Merge parsed metadata with provided metadata
                    if metadata is None:
                        metadata = {}
                    metadata.update(parsed_metadata)
                    
                    # Store pairs for later artifact creation
                    self._temp_pairs = pairs
                    self._temp_parsed_metadata = parsed_metadata
                    
                except TimeoutError as e:
                    logger.error(f"Document parsing timed out for {source}: {e}")
                    # Get page count for helpful error message
                    try:
                        from pdf2image import pdfinfo_from_path
                        info = pdfinfo_from_path(str(source_path))
                        page_count = info.get('Pages', 'unknown')
                        logger.error(f"Document has {page_count} pages. Consider using --timeout or --timeout-per-page to increase limits.")
                    except:
                        pass
                    raise
                except Exception as e:
                    logger.error(f"Document parsing failed for {source}: {e}")
                    # Fall back to reading as text if parsing fails
                    if str(source_path).endswith('.pdf'):
                        raise  # Don't fall back for PDFs
                    content = source_path.read_text(encoding='utf-8', errors='ignore')
                    self._temp_pairs = []
                    self._temp_parsed_metadata = {}
            
            # Update progress to change detection stage
            self.progress_monitor.update_stage(temp_doc_id, "change_detection")
            
            # Analyze changes (use content hash for change detection)
            change_analysis = self.change_detector.analyze_changes(
                source, content, metadata
            )
            
            logger.info(
                f"Change analysis for {source_path.name}: "
                f"{change_analysis.change_type.value} -> {change_analysis.update_strategy.value}"
            )
            
            # Skip if no changes and not forced
            if (change_analysis.update_strategy == UpdateStrategy.SKIP and 
                not force_reprocess):
                self.processing_stats["documents_skipped"] += 1
                self.progress_monitor.complete_document(temp_doc_id, 0, False)
                return {
                    "status": "skipped",
                    "reason": "no_changes_detected",
                    "doc_id": change_analysis.doc_id,
                    "processing_time": time.time() - start_time
                }
            
            # Update progress to registration stage
            self.progress_monitor.update_stage(temp_doc_id, "registration")
            
            # Register document in registry
            doc_id = self._register_document(source, content, metadata)
            
            # Create storage artifact if we have parsed content
            if hasattr(self, '_temp_pairs'):
                try:
                    self.progress_monitor.update_stage(temp_doc_id, "save_artifact")
                    artifact_created = await self._create_storage_artifact(
                        doc_id, source, content, self._temp_pairs, self._temp_parsed_metadata
                    )
                    if not artifact_created:
                        logger.warning(f"Failed to create storage artifact for {doc_id}")
                except Exception as e:
                    logger.error(f"Artifact creation failed for {doc_id}: {e}")
                finally:
                    # Clean up temporary data
                    delattr(self, '_temp_pairs')
                    delattr(self, '_temp_parsed_metadata')
            
            # Update fingerprint
            fingerprint = change_analysis.new_fingerprint
            if fingerprint:
                self.fingerprint_manager.update_fingerprint(
                    fingerprint, doc_id, "processing"
                )
            
            # Process based on update strategy
            result = await self._execute_update_strategy(
                doc_id, source, content, metadata, 
                change_analysis.update_strategy, index_types, with_keywords
            )
            
            # Update processing stats and progress monitoring
            if result["status"] == "success":
                if change_analysis.change_type == ChangeType.NEW_DOCUMENT:
                    self.processing_stats["documents_added"] += 1
                else:
                    self.processing_stats["documents_updated"] += 1
                
                # Update fingerprint status
                if fingerprint:
                    self.fingerprint_manager.update_fingerprint(
                        fingerprint, doc_id, "processed"
                    )
                
                # Mark document as completed
                # Note: chunk count would be available from index manager if needed
                self.progress_monitor.complete_document(temp_doc_id, 0, False)
            else:
                self.processing_stats["processing_errors"] += 1
                
                # Update fingerprint status
                if fingerprint:
                    self.fingerprint_manager.update_fingerprint(
                        fingerprint, doc_id, "failed"
                    )
                
                # Mark document as failed
                self.progress_monitor.fail_document(temp_doc_id, result.get("error", "Unknown error"))
            
            self.processing_stats["documents_processed"] += 1
            result["processing_time"] = time.time() - start_time
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to process document {source}: {e}")
            self.processing_stats["processing_errors"] += 1
            
            # Mark document as failed in progress monitor
            # Use temp_doc_id if available, otherwise generate new one
            fail_doc_id = temp_doc_id if 'temp_doc_id' in locals() else f"temp_{int(time.time()*1000)}"
            self.progress_monitor.fail_document(fail_doc_id, str(e))
            
            return {
                "status": "error",
                "error": str(e),
                "doc_id": "",
                "processing_time": time.time() - start_time
            }
    
    def _register_document(
        self,
        source: Union[str, Path],
        content: str,
        metadata: Optional[Dict[str, Any]]
    ) -> str:
        """Register document in the registry."""
        # Check if source is a URL
        is_url = str(source).startswith(('http://', 'https://'))
        
        # Compute content hash
        import hashlib
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        
        if is_url:
            # For URLs, use content-based metadata
            doc_id = self.registry.register_document(
                source=source,
                content_hash=content_hash,
                size=len(content.encode()),
                modified_time=time.time(),
                metadata=metadata
            )
        else:
            # For local files, use file stats
            source_path = Path(source)
            stat = source_path.stat()
            doc_id = self.registry.register_document(
                source=source,
                content_hash=content_hash,
                size=stat.st_size,
                modified_time=stat.st_mtime,
                metadata=metadata
            )
        
        return doc_id
    
    async def _parse_document_with_openai(
        self,
        source: Union[str, Path],
        doc_id: str,
        mode: str = "auto",
        prompt_file: Optional[str] = None
    ) -> Tuple[str, List[Tuple[str, str]], Dict[str, Any]]:
        """Parse document using OpenAI APIs for PDFs or direct read for text.
        
        Args:
            source: Document path or URL
            doc_id: Document ID for tracking
            mode: Classification mode ('datasheet', 'generic', 'auto')
            prompt_file: Optional custom prompt file path
        """
        # Check if source is a URL
        is_url = str(source).startswith(('http://', 'https://'))
        
        if is_url:
            # Fetch document from URL
            try:
                source_path, _, content_bytes = await fetch_document(source)
                # source_path is now a temporary file
            except Exception as e:
                logger.error(f"Failed to fetch document from URL {source}: {e}")
                raise
        else:
            source_path = Path(source)
            if not source_path.exists():
                raise FileNotFoundError(f"Source file not found: {source}")
        
        # Classify document type based on mode
        is_datasheet_mode = mode == "datasheet" or (mode == "auto" and "datasheet" in str(source).lower())
        doc_type = DocumentClassifier.classify(source, is_datasheet_mode=is_datasheet_mode)
        
        # For PDFs, use fetch_document and parse_document
        if doc_type.name.endswith('_PDF'):
            # Get PDF path and bytes using fetch_document
            pdf_path, _, raw_bytes = await fetch_document(source)
            
            # Load prompt from file or use appropriate default
            if prompt_file and Path(prompt_file).exists():
                prompt_text = Path(prompt_file).read_text()
            elif mode == "generic" and self.config.parser.generic_prompt_path:
                generic_prompt = Path(self.config.parser.generic_prompt_path)
                if generic_prompt.exists():
                    prompt_text = generic_prompt.read_text()
                else:
                    prompt_text = """Please convert this document to clean markdown format."""
            elif is_datasheet_mode and self.config.parser.datasheet_prompt_path:
                datasheet_prompt = Path(self.config.parser.datasheet_prompt_path)
                if datasheet_prompt.exists():
                    prompt_text = datasheet_prompt.read_text()
                else:
                    prompt_text = """Please analyze this technical datasheet and extract information in JSON format with:
                    1. "pairs": Array of [model, part_number] pairs found in the document
                    2. "markdown": Full document content converted to markdown
                    """
            else:
                # Default prompt
                prompt_text = """Please analyze this document and extract information in JSON format with:
                1. "pairs": Array of [model, part_number] pairs found in the document
                2. "markdown": Full document content converted to markdown
                """
            
            # Parse using OpenAI
            markdown, pairs, metadata = await parse_document(
                pdf_path, doc_type, prompt_text, self.cache, self.config
            )
            
            # Clean up temporary file if created
            if pdf_path != source_path:
                try:
                    pdf_path.unlink()
                except:
                    pass
                    
            return markdown, pairs, metadata
        
        else:
            # For markdown/text files, read directly
            content = source_path.read_text(encoding='utf-8', errors='ignore')
            metadata = {
                "source_type": "markdown",
                "file_name": source_path.name,
                "file_size": source_path.stat().st_size,
                "content_length": len(content),
                "doc_type": doc_type.value
            }
            
            # Clean up temporary file if from URL
            if is_url:
                try:
                    source_path.unlink()
                except:
                    pass
            
            return content, [], metadata
    
    async def _create_storage_artifact(
        self,
        doc_id: str,
        source: Union[str, Path],
        markdown: str,
        pairs: List[Tuple[str, str]],
        metadata: Dict[str, Any]
    ) -> bool:
        """Create JSONL storage artifact."""
        try:
            # Ensure storage directory exists
            storage_dir = Path(self.config.storage.base_dir)
            storage_dir.mkdir(parents=True, exist_ok=True)
            
            # Create artifact
            artifact = DatasheetArtefact(
                doc_id=doc_id,
                source=str(source),
                pairs=pairs,
                markdown=markdown,
                parse_version=2,
                metadata=metadata
            )
            
            # Save to storage
            artifact_path = storage_dir / f"{doc_id}.jsonl"
            artifact_path.write_text(artifact.to_jsonl())
            
            logger.info(f"Created storage artifact: {artifact_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create storage artifact for {doc_id}: {e}")
            return False
    
    async def _execute_update_strategy(
        self,
        doc_id: str,
        source: Union[str, Path],
        content: str,
        metadata: Optional[Dict[str, Any]],
        strategy: UpdateStrategy,
        index_types: IndexType,
        with_keywords: bool = False
    ) -> Dict[str, Any]:
        """Execute the determined update strategy."""
        try:
            if strategy == UpdateStrategy.SKIP:
                return {"status": "skipped", "doc_id": doc_id}
            
            elif strategy == UpdateStrategy.REMOVE:
                success = self.index_manager.remove_document(doc_id, index_types)
                return {
                    "status": "success" if success else "error",
                    "action": "removed",
                    "doc_id": doc_id
                }
            
            elif strategy == UpdateStrategy.INCREMENTAL:
                # For now, incremental updates are treated as full reindex
                # In a more sophisticated implementation, this would update only changed chunks
                return await self._full_reindex(doc_id, content, metadata, index_types, source, with_keywords)
            
            elif strategy == UpdateStrategy.FULL_REINDEX:
                return await self._full_reindex(doc_id, content, metadata, index_types, source, with_keywords)
            
            else:
                raise ValueError(f"Unknown update strategy: {strategy}")
                
        except Exception as e:
            logger.error(f"Failed to execute update strategy {strategy}: {e}")
            self.registry.update_document_state(
                doc_id, DocumentState.CORRUPTED, str(e)
            )
            return {"status": "error", "error": str(e), "doc_id": doc_id}
    
    async def _full_reindex(
        self,
        doc_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]],
        index_types: IndexType,
        source: Optional[Union[str, Path]] = None,
        with_keywords: bool = False
    ) -> Dict[str, Any]:
        """Perform full reindexing of document."""
        try:
            # Update document state
            self.registry.update_document_state(doc_id, DocumentState.UPDATING)
            
            # Remove existing entries if they exist
            self.index_manager.remove_document(doc_id, index_types)
            
            # Note: Progress monitoring for indexing handled at higher level
            
            # Add document to indexes - use keyword enhancement if enabled
            if with_keywords:
                # Import chunking_metadata here to avoid circular imports
                from utils.chunking_metadata import process_and_index_document
                
                # Extract pairs from metadata for enhanced processing
                pairs = metadata.get('pairs', []) if metadata else []
                
                # Process with keyword enhancement
                nodes = await process_and_index_document(
                    doc_id=doc_id,
                    source=source or "unknown",
                    markdown=content,
                    pairs=pairs,
                    metadata=metadata or {},
                    with_keywords=True,
                    progress=None,  # Progress monitoring handled at higher level
                    config=self.config
                )
                
                # Add enhanced nodes to indexes
                success = self.index_manager.add_nodes(doc_id, nodes, index_types)
                logger.info(f"Added document {doc_id[:8]} with keyword enhancement ({len(nodes)} chunks)")
            else:
                # Use direct indexing without keyword enhancement
                success = self.index_manager.add_document(
                    doc_id, content, metadata, index_types
                )
            
            # Note: Progress monitoring for indexing handled at higher level
            
            if success:
                self.registry.update_document_state(doc_id, DocumentState.INDEXED)
                return {
                    "status": "success",
                    "action": "indexed",
                    "doc_id": doc_id,
                    "index_types": index_types.value
                }
            else:
                self.registry.update_document_state(
                    doc_id, DocumentState.CORRUPTED, "Indexing failed"
                )
                return {
                    "status": "error",
                    "error": "indexing_failed",
                    "doc_id": doc_id
                }
                
        except Exception as e:
            logger.error(f"Full reindex failed for {doc_id}: {e}")
            self.registry.update_document_state(
                doc_id, DocumentState.CORRUPTED, str(e)
            )
            return {"status": "error", "error": str(e), "doc_id": doc_id}
    
    async def process_document_batch(
        self,
        documents: List[Dict[str, Any]],
        use_queue: bool = True,
        max_concurrent: Optional[int] = None
    ) -> Dict[str, Any]:
        """Process multiple documents efficiently."""
        if use_queue:
            return await self._process_batch_with_queue(documents, max_concurrent)
        else:
            return await self._process_batch_direct(documents, max_concurrent)
    
    async def _process_batch_with_queue(
        self,
        documents: List[Dict[str, Any]],
        max_concurrent: Optional[int] = None
    ) -> Dict[str, Any]:
        """Process documents using the job queue system."""
        start_time = time.time()
        
        # Analyze changes for all documents
        analyses = self.change_detector.batch_analyze_changes(documents)
        
        # Create jobs with appropriate priorities
        job_ids = []
        for analysis in analyses:
            if analysis.update_strategy != UpdateStrategy.SKIP:
                priority = self._convert_priority(analysis.processing_priority)
                
                job_id = await self.document_queue.add_job(
                    source=analysis.source,
                    job_type="process",
                    priority=priority,
                    metadata={
                        "doc_id": analysis.doc_id,
                        "update_strategy": analysis.update_strategy.value,
                        "estimated_effort": analysis.estimated_effort
                    }
                )
                job_ids.append(job_id)
        
        logger.info(f"Queued {len(job_ids)} documents for processing")
        
        # Start queue processing if not already running
        if not self.document_queue.workers:
            processing_task = asyncio.create_task(
                self.document_queue.start_processing()
            )
            
            # Wait for completion or timeout
            try:
                batch_timeout = self.config.pipeline.timeout_seconds
                await asyncio.wait_for(processing_task, timeout=batch_timeout)
            except asyncio.TimeoutError:
                logger.warning(f"Batch processing timeout after {batch_timeout}s - some jobs may still be running")
        
        # Get final status
        queue_status = self.document_queue.get_status()
        
        return {
            "status": "completed",
            "total_documents": len(documents),
            "jobs_created": len(job_ids),
            "processing_time": time.time() - start_time,
            "queue_status": queue_status,
            "job_ids": job_ids
        }
    
    async def _process_batch_direct(
        self,
        documents: List[Dict[str, Any]],
        max_concurrent: Optional[int] = None
    ) -> Dict[str, Any]:
        """Process documents directly without queue."""
        max_concurrent = max_concurrent or self.config.pipeline.max_concurrent
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def process_single(doc_info):
            async with semaphore:
                return await self.process_document(
                    source=doc_info["source"],
                    content=doc_info.get("content"),
                    metadata=doc_info.get("metadata", {}),
                    force_reprocess=doc_info.get("force_reprocess", False),
                    mode=doc_info.get("mode", "auto"),
                    prompt_file=doc_info.get("prompt_file"),
                    with_keywords=doc_info.get("with_keywords", False)
                )
        
        start_time = time.time()
        
        # Process all documents concurrently
        tasks = [process_single(doc) for doc in documents]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Analyze results
        successful = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "success")
        errors = sum(1 for r in results if isinstance(r, Exception) or 
                    (isinstance(r, dict) and r.get("status") == "error"))
        skipped = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "skipped")
        
        return {
            "status": "completed",
            "total_documents": len(documents),
            "successful": successful,
            "errors": errors,
            "skipped": skipped,
            "processing_time": time.time() - start_time,
            "results": results
        }
    
    def _convert_priority(self, analysis_priority: int) -> JobPriority:
        """Convert analysis priority to job priority."""
        priority_map = {
            1: JobPriority.HIGH,
            2: JobPriority.NORMAL,
            3: JobPriority.LOW
        }
        return priority_map.get(analysis_priority, JobPriority.NORMAL)
    
    async def remove_document(
        self,
        source: Union[str, Path],
        index_types: IndexType = IndexType.BOTH
    ) -> Dict[str, Any]:
        """Remove document from indexes and registry."""
        try:
            # Get document from registry
            doc = self.registry.get_document_by_source(source)
            if not doc:
                return {
                    "status": "error",
                    "error": "document_not_found",
                    "source": str(source)
                }
            
            # Remove from indexes
            success = self.index_manager.remove_document(doc.doc_id, index_types)
            
            if success:
                self.processing_stats["documents_removed"] += 1
                return {
                    "status": "success",
                    "action": "removed",
                    "doc_id": doc.doc_id,
                    "source": str(source)
                }
            else:
                return {
                    "status": "error",
                    "error": "removal_failed",
                    "doc_id": doc.doc_id,
                    "source": str(source)
                }
                
        except Exception as e:
            logger.error(f"Failed to remove document {source}: {e}")
            return {
                "status": "error",
                "error": str(e),
                "source": str(source)
            }
    
    def search(
        self,
        query: str,
        search_type: str = "hybrid",
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Search documents using specified method."""
        try:
            if search_type == "vector":
                return self.index_manager.search_vector(query, top_k, filters=filters, **kwargs)
            elif search_type == "keyword":
                return self.index_manager.search_keyword(query, top_k, filters=filters, **kwargs)
            elif search_type == "hybrid":
                return self.index_manager.hybrid_search(query, top_k, filters=filters, **kwargs)
            else:
                raise ValueError(f"Unknown search type: {search_type}")
                
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []
    
    def get_comprehensive_status(self) -> Dict[str, Any]:
        """Get comprehensive pipeline status."""
        try:
            return {
                "pipeline": {
                    "is_processing": self.is_processing,
                    "processing_stats": self.processing_stats
                },
                "queue": self.document_queue.get_status(),
                "jobs": self.job_manager.get_job_statistics(),
                "indexes": self.index_manager.get_statistics(),
                "registry": self.registry.get_statistics(),
                "consistency": self.index_manager.verify_consistency(),
                "timestamp": time.time()
            }
            
        except Exception as e:
            logger.error(f"Failed to get comprehensive status: {e}")
            return {"error": str(e)}
    
    def get_update_recommendations(
        self,
        time_budget: float = 300.0,
        max_documents: int = 50
    ) -> Dict[str, Any]:
        """Get intelligent update recommendations."""
        return self.change_detector.get_update_recommendations(
            time_budget, max_documents
        )
    
    async def perform_maintenance(self) -> Dict[str, Any]:
        """Perform system maintenance and consistency checks."""
        maintenance_results = {
            "consistency_check": None,
            "index_repair": None,
            "registry_cleanup": None,
            "fingerprint_cleanup": None,
            "job_cleanup": None,
            "timestamp": time.time()
        }
        
        try:
            # Consistency check
            maintenance_results["consistency_check"] = self.index_manager.verify_consistency()
            
            # Repair indexes if needed
            consistency = maintenance_results["consistency_check"]
            if (consistency.get("overall_health", {}).get("score", 0) < 90):
                maintenance_results["index_repair"] = self.index_manager.repair_indexes()
            
            # Registry cleanup
            maintenance_results["registry_cleanup"] = self.registry.cleanup_orphaned_entries()
            
            # Fingerprint cleanup
            maintenance_results["fingerprint_cleanup"] = self.fingerprint_manager.cleanup_old_fingerprints()
            
            # Job cleanup
            maintenance_results["job_cleanup"] = self.job_manager.cleanup_completed_jobs()
            
            logger.info("System maintenance completed successfully")
            
        except Exception as e:
            logger.error(f"Maintenance failed: {e}")
            maintenance_results["error"] = str(e)
        
        return maintenance_results
    
    async def shutdown(self) -> None:
        """Gracefully shutdown the pipeline."""
        logger.info("Shutting down enhanced pipeline...")
        
        # Stop queue processing
        await self.document_queue.shutdown()
        
        # Close all components
        self.job_manager.close()
        self.fingerprint_manager.close()
        self.index_manager.close()
        self.registry.close()
        self.change_detector.close()
        
        logger.info("Enhanced pipeline shutdown complete")
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.shutdown()
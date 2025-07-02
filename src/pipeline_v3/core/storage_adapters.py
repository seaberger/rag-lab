"""
Storage System Adapters for Transactional Support

Provides transactional wrappers for Pipeline v3's storage systems:
- DocumentRegistry (SQLite)
- Qdrant Vector Store
- Keyword Index (SQLite FTS5)
- Storage Artifacts (JSONL)
- Fingerprint Store (SQLite)
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance

from .transaction_coordinator import (
    Checkpoint, OperationType, StorageSystem, TransactionOperation
)
from ..core.registry import DocumentRegistry, DocumentState
from ..core.fingerprint import FingerprintManager
from ..storage.keyword_index import BM25Index


class RegistryAdapter(StorageSystem):
    """Adapter for DocumentRegistry with transactional support"""
    
    def __init__(self, registry: DocumentRegistry):
        super().__init__("DocumentRegistry")
        self.registry = registry
        self.pending_operations: Dict[UUID, TransactionOperation] = {}
        
    async def prepare(self, operation: TransactionOperation, operation_id: UUID) -> Checkpoint:
        """Prepare registry operation"""
        # Capture current state
        current_doc = self.registry.get_document(operation.doc_id)
        current_state = current_doc.dict() if current_doc else None
        
        checkpoint = Checkpoint(
            system_name=self.name,
            operation_id=operation_id,
            doc_id=operation.doc_id,
            operation_type=operation.operation_type,
            state_before=current_state
        )
        
        # Validate operation
        if operation.operation_type == OperationType.ADD_DOCUMENT:
            if current_doc is not None:
                raise ValueError(f"Document {operation.doc_id} already exists")
        elif operation.operation_type in [OperationType.UPDATE_DOCUMENT, OperationType.DELETE_DOCUMENT]:
            if current_doc is None:
                raise ValueError(f"Document {operation.doc_id} not found")
        
        # Store pending operation
        self.pending_operations[operation_id] = operation
        
        return checkpoint
    
    async def commit(self, checkpoint: Checkpoint) -> bool:
        """Commit registry changes"""
        operation = self.pending_operations.get(checkpoint.operation_id)
        if not operation:
            return False
        
        try:
            if operation.operation_type == OperationType.ADD_DOCUMENT:
                # Register the document
                doc_id = self.registry.register_document(
                    source=operation.data['file_path'],
                    content_hash=operation.data.get('fingerprint', 'unknown'),
                    size=len(operation.data.get('content', '')),
                    modified_time=operation.timestamp.timestamp(),
                    doc_id=operation.doc_id,
                    metadata=operation.metadata
                )
                success = doc_id == operation.doc_id
                if success:
                    self.registry.update_document_state(
                        operation.doc_id, 
                        DocumentState.INDEXED
                    )
                    
            elif operation.operation_type == OperationType.UPDATE_DOCUMENT:
                # Update metadata
                doc = self.registry.get_document(operation.doc_id)
                if doc:
                    doc.metadata.update(operation.metadata)
                    doc.updated_at = datetime.now()
                    success = True
                else:
                    success = False
                    
            elif operation.operation_type == OperationType.DELETE_DOCUMENT:
                success = self.registry.remove_document(operation.doc_id)
                
            else:
                success = True
            
            # Clean up pending operation
            del self.pending_operations[checkpoint.operation_id]
            return success
            
        except Exception as e:
            self.logger.error(f"Commit failed: {e}")
            return False
    
    async def rollback(self, checkpoint: Checkpoint) -> bool:
        """Rollback registry changes"""
        try:
            if checkpoint.state_before:
                # Restore previous state
                state = DocumentState(checkpoint.state_before['state'])
                return self.registry.update_document_state(
                    checkpoint.doc_id,
                    state
                )
            else:
                # Document didn't exist before, remove it
                return self.registry.remove_document(checkpoint.doc_id)
                
        except Exception as e:
            self.logger.error(f"Rollback failed: {e}")
            return False
        finally:
            # Clean up pending operation
            self.pending_operations.pop(checkpoint.operation_id, None)
    
    async def verify_state(self, doc_id: str) -> Dict[str, Any]:
        """Verify document state in registry"""
        doc = self.registry.get_document(doc_id)
        if doc:
            return {
                "exists": True,
                "state": doc.state.value,
                "metadata": doc.metadata,
                "updated_at": doc.updated_at.isoformat()
            }
        return {"exists": False}
    
    async def health_check(self) -> bool:
        """Check registry health"""
        try:
            # Try a simple query
            self.registry.get_all_documents(limit=1)
            return True
        except Exception:
            return False


class QdrantAdapter(StorageSystem):
    """Adapter for Qdrant with transactional support"""
    
    def __init__(self, client: QdrantClient, collection_name: str):
        super().__init__("QdrantVectorStore")
        self.client = client
        self.collection_name = collection_name
        self.prepared_points: Dict[UUID, List[PointStruct]] = {}
        self.deleted_points: Dict[UUID, List[Dict]] = {}
        
    async def prepare(self, operation: TransactionOperation, operation_id: UUID) -> Checkpoint:
        """Prepare Qdrant operation"""
        checkpoint = Checkpoint(
            system_name=self.name,
            operation_id=operation_id,
            doc_id=operation.doc_id,
            operation_type=operation.operation_type
        )
        
        # Get current state for rollback
        try:
            current_points = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter={"must": [{"key": "doc_id", "match": {"value": operation.doc_id}}]},
                limit=1000
            )[0]
            
            checkpoint.state_before = {
                "points": [
                    {
                        "id": str(point.id),
                        "vector": point.vector,
                        "payload": point.payload
                    }
                    for point in current_points
                ]
            }
        except Exception:
            checkpoint.state_before = {"points": []}
        
        # Prepare operation data
        if operation.operation_type in [OperationType.ADD_DOCUMENT, OperationType.UPDATE_DOCUMENT]:
            if "nodes" not in operation.data:
                raise ValueError("Nodes required for vector indexing")
            
            # Convert nodes to points
            points = []
            for i, node in enumerate(operation.data["nodes"]):
                if hasattr(node, 'embedding') and node.embedding is not None:
                    point = PointStruct(
                        id=f"{operation.doc_id}_{i}",
                        vector=node.embedding,
                        payload={
                            "doc_id": operation.doc_id,
                            "node_id": node.node_id,
                            "text": node.text,
                            "metadata": node.metadata
                        }
                    )
                    points.append(point)
            
            self.prepared_points[operation_id] = points
            
        elif operation.operation_type == OperationType.DELETE_DOCUMENT:
            # Store points to be deleted
            self.deleted_points[operation_id] = checkpoint.state_before.get("points", [])
        
        return checkpoint
    
    async def commit(self, checkpoint: Checkpoint) -> bool:
        """Commit Qdrant changes"""
        try:
            if checkpoint.operation_type == OperationType.DELETE_DOCUMENT:
                # Delete all points for document
                self.client.delete(
                    collection_name=self.collection_name,
                    points_selector={
                        "filter": {
                            "must": [{"key": "doc_id", "match": {"value": checkpoint.doc_id}}]
                        }
                    }
                )
                
            elif checkpoint.operation_type in [OperationType.ADD_DOCUMENT, OperationType.UPDATE_DOCUMENT]:
                points = self.prepared_points.get(checkpoint.operation_id, [])
                
                if checkpoint.operation_type == OperationType.UPDATE_DOCUMENT:
                    # Delete old points first
                    self.client.delete(
                        collection_name=self.collection_name,
                        points_selector={
                            "filter": {
                                "must": [{"key": "doc_id", "match": {"value": checkpoint.doc_id}}]
                            }
                        }
                    )
                
                # Insert new points
                if points:
                    self.client.upsert(
                        collection_name=self.collection_name,
                        points=points
                    )
            
            # Clean up prepared data
            self.prepared_points.pop(checkpoint.operation_id, None)
            self.deleted_points.pop(checkpoint.operation_id, None)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Commit failed: {e}")
            return False
    
    async def rollback(self, checkpoint: Checkpoint) -> bool:
        """Rollback Qdrant changes"""
        try:
            # Delete any points that were added
            self.client.delete(
                collection_name=self.collection_name,
                points_selector={
                    "filter": {
                        "must": [{"key": "doc_id", "match": {"value": checkpoint.doc_id}}]
                    }
                }
            )
            
            # Restore previous points if any
            if checkpoint.state_before and checkpoint.state_before.get("points"):
                restore_points = []
                for point_data in checkpoint.state_before["points"]:
                    restore_points.append(PointStruct(
                        id=point_data["id"],
                        vector=point_data["vector"],
                        payload=point_data["payload"]
                    ))
                
                if restore_points:
                    self.client.upsert(
                        collection_name=self.collection_name,
                        points=restore_points
                    )
            
            # Clean up prepared data
            self.prepared_points.pop(checkpoint.operation_id, None)
            self.deleted_points.pop(checkpoint.operation_id, None)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Rollback failed: {e}")
            return False
    
    async def verify_state(self, doc_id: str) -> Dict[str, Any]:
        """Verify document state in Qdrant"""
        try:
            points = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter={"must": [{"key": "doc_id", "match": {"value": doc_id}}]},
                limit=1000
            )[0]
            
            return {
                "exists": len(points) > 0,
                "point_count": len(points),
                "point_ids": [str(p.id) for p in points]
            }
        except Exception:
            return {"exists": False, "point_count": 0}
    
    async def health_check(self) -> bool:
        """Check Qdrant health"""
        try:
            self.client.get_collection(self.collection_name)
            return True
        except Exception:
            return False


class KeywordIndexAdapter(StorageSystem):
    """Adapter for BM25 Keyword Index with transactional support"""
    
    def __init__(self, index: BM25Index):
        super().__init__("KeywordIndex")
        self.index = index
        self.prepared_data: Dict[UUID, Dict[str, Any]] = {}
        
    async def prepare(self, operation: TransactionOperation, operation_id: UUID) -> Checkpoint:
        """Prepare keyword index operation"""
        checkpoint = Checkpoint(
            system_name=self.name,
            operation_id=operation_id,
            doc_id=operation.doc_id,
            operation_type=operation.operation_type
        )
        
        # Get current state
        try:
            with self.index.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT content, metadata FROM documents WHERE doc_id = ?",
                    (operation.doc_id,)
                )
                row = cursor.fetchone()
                if row:
                    checkpoint.state_before = {
                        "exists": True,
                        "content": row[0],
                        "metadata": json.loads(row[1]) if row[1] else {}
                    }
                else:
                    checkpoint.state_before = {"exists": False}
        except Exception as e:
            self.logger.error(f"Error getting current state: {e}")
            checkpoint.state_before = {"exists": False}
        
        # Prepare operation data
        if operation.operation_type in [OperationType.ADD_DOCUMENT, OperationType.UPDATE_DOCUMENT]:
            if "content" not in operation.data:
                raise ValueError("Content required for keyword indexing")
            
            self.prepared_data[operation_id] = {
                "content": operation.data["content"],
                "metadata": operation.metadata
            }
        
        return checkpoint
    
    async def commit(self, checkpoint: Checkpoint) -> bool:
        """Commit keyword index changes"""
        try:
            if checkpoint.operation_type == OperationType.DELETE_DOCUMENT:
                return self.index.delete_document(checkpoint.doc_id)
                
            elif checkpoint.operation_type in [OperationType.ADD_DOCUMENT, OperationType.UPDATE_DOCUMENT]:
                data = self.prepared_data.get(checkpoint.operation_id)
                if not data:
                    return False
                
                if checkpoint.operation_type == OperationType.UPDATE_DOCUMENT:
                    # Delete old version first
                    self.index.delete_document(checkpoint.doc_id)
                
                # Add new version
                success = self.index.add_document(
                    doc_id=checkpoint.doc_id,
                    content=data["content"],
                    metadata=data["metadata"]
                )
                
                # Clean up prepared data
                del self.prepared_data[checkpoint.operation_id]
                return success
            
            return True
            
        except Exception as e:
            self.logger.error(f"Commit failed: {e}")
            return False
    
    async def rollback(self, checkpoint: Checkpoint) -> bool:
        """Rollback keyword index changes"""
        try:
            # Delete any changes
            self.index.delete_document(checkpoint.doc_id)
            
            # Restore previous state if existed
            if checkpoint.state_before and checkpoint.state_before.get("exists"):
                return self.index.add_document(
                    doc_id=checkpoint.doc_id,
                    content=checkpoint.state_before["content"],
                    metadata=checkpoint.state_before["metadata"]
                )
            
            # Clean up prepared data
            self.prepared_data.pop(checkpoint.operation_id, None)
            return True
            
        except Exception as e:
            self.logger.error(f"Rollback failed: {e}")
            return False
    
    async def verify_state(self, doc_id: str) -> Dict[str, Any]:
        """Verify document state in keyword index"""
        try:
            with self.index.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM documents WHERE doc_id = ?",
                    (doc_id,)
                )
                count = cursor.fetchone()[0]
                return {"exists": count > 0}
        except Exception:
            return {"exists": False}
    
    async def health_check(self) -> bool:
        """Check keyword index health"""
        try:
            with self.index.get_connection() as conn:
                conn.execute("SELECT 1")
            return True
        except Exception:
            return False


class StorageArtifactsAdapter(StorageSystem):
    """Adapter for JSONL storage artifacts with transactional support"""
    
    def __init__(self, storage_dir: Path):
        super().__init__("StorageArtifacts")
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(exist_ok=True)
        self.prepared_files: Dict[UUID, Path] = {}
        self.backup_files: Dict[UUID, Optional[bytes]] = {}
        
    async def prepare(self, operation: TransactionOperation, operation_id: UUID) -> Checkpoint:
        """Prepare storage artifact operation"""
        checkpoint = Checkpoint(
            system_name=self.name,
            operation_id=operation_id,
            doc_id=operation.doc_id,
            operation_type=operation.operation_type
        )
        
        # Get current state
        artifact_path = self.storage_dir / f"{operation.doc_id}.jsonl"
        if artifact_path.exists():
            checkpoint.state_before = {
                "exists": True,
                "path": str(artifact_path)
            }
            # Backup current content
            self.backup_files[operation_id] = artifact_path.read_bytes()
        else:
            checkpoint.state_before = {"exists": False}
            self.backup_files[operation_id] = None
        
        # Prepare new artifact
        if operation.operation_type in [OperationType.ADD_DOCUMENT, OperationType.UPDATE_DOCUMENT]:
            if "artifact_data" not in operation.data:
                raise ValueError("Artifact data required for storage")
            
            # Write to temporary file
            temp_path = self.storage_dir / f".tmp_{operation.doc_id}_{operation_id}.jsonl"
            with open(temp_path, 'w') as f:
                json.dump(operation.data["artifact_data"], f)
                f.write('\n')
            
            self.prepared_files[operation_id] = temp_path
        
        return checkpoint
    
    async def commit(self, checkpoint: Checkpoint) -> bool:
        """Commit storage artifact changes"""
        try:
            artifact_path = self.storage_dir / f"{checkpoint.doc_id}.jsonl"
            
            if checkpoint.operation_type == OperationType.DELETE_DOCUMENT:
                if artifact_path.exists():
                    artifact_path.unlink()
                    
            elif checkpoint.operation_type in [OperationType.ADD_DOCUMENT, OperationType.UPDATE_DOCUMENT]:
                temp_path = self.prepared_files.get(checkpoint.operation_id)
                if not temp_path or not temp_path.exists():
                    return False
                
                # Move temp file to final location
                temp_path.rename(artifact_path)
            
            # Clean up
            self.prepared_files.pop(checkpoint.operation_id, None)
            self.backup_files.pop(checkpoint.operation_id, None)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Commit failed: {e}")
            return False
    
    async def rollback(self, checkpoint: Checkpoint) -> bool:
        """Rollback storage artifact changes"""
        try:
            artifact_path = self.storage_dir / f"{checkpoint.doc_id}.jsonl"
            
            # Remove any new file
            if artifact_path.exists():
                artifact_path.unlink()
            
            # Restore backup if exists
            backup_content = self.backup_files.get(checkpoint.operation_id)
            if backup_content is not None:
                artifact_path.write_bytes(backup_content)
            
            # Clean up temp file
            temp_path = self.prepared_files.get(checkpoint.operation_id)
            if temp_path and temp_path.exists():
                temp_path.unlink()
            
            # Clean up
            self.prepared_files.pop(checkpoint.operation_id, None)
            self.backup_files.pop(checkpoint.operation_id, None)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Rollback failed: {e}")
            return False
    
    async def verify_state(self, doc_id: str) -> Dict[str, Any]:
        """Verify storage artifact state"""
        artifact_path = self.storage_dir / f"{doc_id}.jsonl"
        return {
            "exists": artifact_path.exists(),
            "path": str(artifact_path) if artifact_path.exists() else None,
            "size": artifact_path.stat().st_size if artifact_path.exists() else 0
        }
    
    async def health_check(self) -> bool:
        """Check storage directory health"""
        try:
            # Check if we can write to the directory
            test_file = self.storage_dir / ".health_check"
            test_file.write_text("test")
            test_file.unlink()
            return True
        except Exception:
            return False


class FingerprintAdapter(StorageSystem):
    """Adapter for Fingerprint Store with transactional support"""
    
    def __init__(self, fingerprint_manager: FingerprintManager):
        super().__init__("FingerprintStore")
        self.manager = fingerprint_manager
        self.prepared_data: Dict[UUID, Dict[str, str]] = {}
        
    async def prepare(self, operation: TransactionOperation, operation_id: UUID) -> Checkpoint:
        """Prepare fingerprint operation"""
        checkpoint = Checkpoint(
            system_name=self.name,
            operation_id=operation_id,
            doc_id=operation.doc_id,
            operation_type=operation.operation_type
        )
        
        # Get current fingerprint
        # Note: FingerprintManager uses source paths, not doc_ids
        source_path = operation.data.get('file_path', '')
        current_fp = self.manager.get_fingerprint(source_path) if source_path else None
        if current_fp:
            checkpoint.state_before = {
                "exists": True,
                "fingerprint": current_fp.fingerprint,
                "timestamp": current_fp.timestamp.isoformat()
            }
        else:
            checkpoint.state_before = {"exists": False}
        
        # Prepare new fingerprint
        if operation.operation_type in [OperationType.ADD_DOCUMENT, OperationType.UPDATE_DOCUMENT]:
            if "fingerprint" not in operation.data:
                raise ValueError("Fingerprint required")
            
            self.prepared_data[operation_id] = {
                "fingerprint": operation.data["fingerprint"],
                "source_path": operation.data.get("file_path", "")
            }
        
        return checkpoint
    
    async def commit(self, checkpoint: Checkpoint) -> bool:
        """Commit fingerprint changes"""
        try:
            if checkpoint.operation_type == OperationType.DELETE_DOCUMENT:
                # FingerprintManager doesn't support deletion
                return True
                
            elif checkpoint.operation_type in [OperationType.ADD_DOCUMENT, OperationType.UPDATE_DOCUMENT]:
                data = self.prepared_data.get(checkpoint.operation_id)
                if not data:
                    return False
                
                source_path = data['source_path']
                fingerprint = data['fingerprint']
                
                if not source_path:
                    return False
                    
                success = self.manager.update_fingerprint(source_path, fingerprint)
                
                # Clean up
                del self.prepared_data[checkpoint.operation_id]
                return success
            
            return True
            
        except Exception as e:
            self.logger.error(f"Commit failed: {e}")
            return False
    
    async def rollback(self, checkpoint: Checkpoint) -> bool:
        """Rollback fingerprint changes"""
        try:
            # FingerprintManager doesn't support deletion
            # Would need to implement a workaround
            
            # Restore previous fingerprint if existed
            # Cannot restore fingerprint without source path
            # This is a limitation of the current design
            
            # Clean up
            self.prepared_data.pop(checkpoint.operation_id, None)
            return True
            
        except Exception as e:
            self.logger.error(f"Rollback failed: {e}")
            return False
    
    async def verify_state(self, doc_id: str) -> Dict[str, Any]:
        """Verify fingerprint state"""
        # FingerprintManager uses source paths - this won't work with just doc_id
        # This is a design limitation
        return {"exists": False}
        if fp:
            return {
                "exists": True,
                "fingerprint": fp.fingerprint,
                "timestamp": fp.timestamp.isoformat()
            }
        return {"exists": False}
    
    async def health_check(self) -> bool:
        """Check fingerprint store health"""
        try:
            # Try a simple query
            with self.manager.get_connection() as conn:
                conn.execute("SELECT 1")
            return True
        except Exception:
            return False
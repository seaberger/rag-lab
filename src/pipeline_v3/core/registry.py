"""
Document Registry - Phase 2 Implementation

Central registry for tracking document states across vector and keyword indexes.
Ensures consistency and enables intelligent lifecycle management operations.
"""

import json
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

# Add parent directory to path for imports
import sys
sys.path.append(str(Path(__file__).parent.parent))

from utils.common_utils import logger
from utils.config import PipelineConfig


class DocumentState(Enum):
    """Document processing states."""
    NEW = "new"
    INDEXED = "indexed"
    UPDATING = "updating"
    STALE = "stale"
    CORRUPTED = "corrupted"
    REMOVED = "removed"


class IndexType(Enum):
    """Types of indexes."""
    VECTOR = "vector"
    KEYWORD = "keyword"
    BOTH = "both"


@dataclass
class DocumentRecord:
    """Represents a document record in the registry."""
    doc_id: str
    source: str
    content_hash: str
    size: int
    modified_time: float
    created_at: float
    updated_at: float
    state: str = DocumentState.NEW.value
    vector_indexed: bool = False
    keyword_indexed: bool = False
    chunk_count: int = 0
    error_count: int = 0
    last_error: Optional[str] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class IndexRecord:
    """Represents an index entry for a document."""
    doc_id: str
    index_type: str
    node_id: str
    chunk_index: int
    content_hash: str
    created_at: float
    updated_at: float
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class DocumentRegistry:
    """Central registry for document and index state management."""
    
    def __init__(self, config: Optional[PipelineConfig] = None):
        """Initialize document registry with configuration."""
        self.config = config or PipelineConfig()
        
        # Use configured storage path
        self.storage_path = Path(self.config.storage.document_registry_path)
        
        # Initialize database
        self._init_database()
        
        logger.info(f"DocumentRegistry initialized with storage: {self.storage_path}")
    
    def _init_database(self) -> None:
        """Initialize SQLite database for document registry."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.conn = sqlite3.connect(str(self.storage_path))
        
        # Documents table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                doc_id TEXT PRIMARY KEY,
                source TEXT UNIQUE NOT NULL,
                content_hash TEXT NOT NULL,
                size INTEGER NOT NULL,
                modified_time REAL NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                state TEXT NOT NULL,
                vector_indexed BOOLEAN NOT NULL DEFAULT 0,
                keyword_indexed BOOLEAN NOT NULL DEFAULT 0,
                chunk_count INTEGER NOT NULL DEFAULT 0,
                error_count INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                metadata TEXT  -- JSON
            )
        """)
        
        # Index entries table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS index_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id TEXT NOT NULL,
                index_type TEXT NOT NULL,
                node_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                content_hash TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                metadata TEXT,  -- JSON
                FOREIGN KEY (doc_id) REFERENCES documents (doc_id),
                UNIQUE(doc_id, index_type, chunk_index)
            )
        """)
        
        # Create indexes for performance
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source)
        """)
        
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_documents_state ON documents(state)
        """)
        
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_documents_content_hash ON documents(content_hash)
        """)
        
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_index_entries_doc_id ON index_entries(doc_id)
        """)
        
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_index_entries_type ON index_entries(index_type)
        """)
        
        self.conn.commit()
        logger.info("Document registry database initialized")
    
    def register_document(
        self, 
        source: Union[str, Path],
        content_hash: str,
        size: int,
        modified_time: float,
        doc_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Register a new document or update existing one."""
        if doc_id is None:
            doc_id = str(uuid.uuid4())
        
        current_time = time.time()
        source_key = str(Path(source).resolve())
        
        # Check if document already exists
        existing = self.get_document_by_source(source)
        
        if existing:
            # Update existing document
            existing.content_hash = content_hash
            existing.size = size
            existing.modified_time = modified_time
            existing.updated_at = current_time
            existing.metadata = metadata or existing.metadata
            
            # Reset indexing flags if content changed
            if existing.content_hash != content_hash:
                existing.vector_indexed = False
                existing.keyword_indexed = False
                existing.chunk_count = 0
                existing.state = DocumentState.STALE.value
                logger.info(f"Document content changed, marking as stale: {source}")
            
            self._save_document(existing)
            return existing.doc_id
        else:
            # Create new document record
            doc = DocumentRecord(
                doc_id=doc_id,
                source=source_key,
                content_hash=content_hash,
                size=size,
                modified_time=modified_time,
                created_at=current_time,
                updated_at=current_time,
                metadata=metadata or {}
            )
            
            self._save_document(doc)
            logger.info(f"Registered new document: {doc_id[:8]} - {source}")
            return doc_id
    
    def _save_document(self, doc: DocumentRecord) -> None:
        """Save document record to database."""
        self.conn.execute("""
            INSERT OR REPLACE INTO documents
            (doc_id, source, content_hash, size, modified_time, created_at, updated_at,
             state, vector_indexed, keyword_indexed, chunk_count, error_count, last_error, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            doc.doc_id,
            doc.source,
            doc.content_hash,
            doc.size,
            doc.modified_time,
            doc.created_at,
            doc.updated_at,
            doc.state,
            doc.vector_indexed,
            doc.keyword_indexed,
            doc.chunk_count,
            doc.error_count,
            doc.last_error,
            json.dumps(doc.metadata) if doc.metadata else None
        ))
        self.conn.commit()
    
    def get_document(self, doc_id: str) -> Optional[DocumentRecord]:
        """Get document record by ID."""
        cursor = self.conn.execute("""
            SELECT doc_id, source, content_hash, size, modified_time, created_at, updated_at,
                   state, vector_indexed, keyword_indexed, chunk_count, error_count, last_error, metadata
            FROM documents WHERE doc_id = ?
        """, (doc_id,))
        
        row = cursor.fetchone()
        if row:
            return self._row_to_document(row)
        return None
    
    def get_document_by_source(self, source: Union[str, Path]) -> Optional[DocumentRecord]:
        """Get document record by source path."""
        source_key = str(Path(source).resolve())
        
        cursor = self.conn.execute("""
            SELECT doc_id, source, content_hash, size, modified_time, created_at, updated_at,
                   state, vector_indexed, keyword_indexed, chunk_count, error_count, last_error, metadata
            FROM documents WHERE source = ?
        """, (source_key,))
        
        row = cursor.fetchone()
        if row:
            return self._row_to_document(row)
        return None
    
    def _row_to_document(self, row) -> DocumentRecord:
        """Convert database row to DocumentRecord."""
        metadata = json.loads(row[13]) if row[13] else {}
        
        return DocumentRecord(
            doc_id=row[0],
            source=row[1],
            content_hash=row[2],
            size=row[3],
            modified_time=row[4],
            created_at=row[5],
            updated_at=row[6],
            state=row[7],
            vector_indexed=bool(row[8]),
            keyword_indexed=bool(row[9]),
            chunk_count=row[10],
            error_count=row[11],
            last_error=row[12],
            metadata=metadata
        )
    
    def update_document_state(
        self, 
        doc_id: str, 
        state: DocumentState,
        error_message: Optional[str] = None
    ) -> bool:
        """Update document processing state."""
        doc = self.get_document(doc_id)
        if not doc:
            logger.error(f"Document {doc_id} not found for state update")
            return False
        
        doc.state = state.value
        doc.updated_at = time.time()
        
        if error_message:
            doc.error_count += 1
            doc.last_error = error_message
        
        self._save_document(doc)
        logger.debug(f"Updated document {doc_id[:8]} state to {state.value}")
        return True
    
    def mark_indexed(
        self, 
        doc_id: str, 
        index_type: IndexType,
        chunk_count: int = 0
    ) -> bool:
        """Mark document as indexed in specified index type."""
        doc = self.get_document(doc_id)
        if not doc:
            logger.error(f"Document {doc_id} not found for indexing update")
            return False
        
        if index_type in [IndexType.VECTOR, IndexType.BOTH]:
            doc.vector_indexed = True
        
        if index_type in [IndexType.KEYWORD, IndexType.BOTH]:
            doc.keyword_indexed = True
        
        doc.chunk_count = chunk_count
        doc.state = DocumentState.INDEXED.value
        doc.updated_at = time.time()
        
        self._save_document(doc)
        logger.info(f"Marked document {doc_id[:8]} as indexed ({index_type.value})")
        return True
    
    def register_index_entry(
        self,
        doc_id: str,
        index_type: IndexType,
        node_id: str,
        chunk_index: int,
        content_hash: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Register an index entry for a document chunk."""
        current_time = time.time()
        
        try:
            self.conn.execute("""
                INSERT OR REPLACE INTO index_entries
                (doc_id, index_type, node_id, chunk_index, content_hash, created_at, updated_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                doc_id,
                index_type.value,
                node_id,
                chunk_index,
                content_hash,
                current_time,
                current_time,
                json.dumps(metadata) if metadata else None
            ))
            self.conn.commit()
            return True
            
        except Exception as e:
            logger.error(f"Failed to register index entry: {e}")
            return False
    
    def get_index_entries(
        self, 
        doc_id: str, 
        index_type: Optional[IndexType] = None
    ) -> List[IndexRecord]:
        """Get index entries for a document."""
        query = """
            SELECT doc_id, index_type, node_id, chunk_index, content_hash, created_at, updated_at, metadata
            FROM index_entries WHERE doc_id = ?
        """
        params = [doc_id]
        
        if index_type:
            query += " AND index_type = ?"
            params.append(index_type.value)
        
        query += " ORDER BY chunk_index"
        
        cursor = self.conn.execute(query, params)
        
        entries = []
        for row in cursor.fetchall():
            metadata = json.loads(row[7]) if row[7] else {}
            entries.append(IndexRecord(
                doc_id=row[0],
                index_type=row[1],
                node_id=row[2],
                chunk_index=row[3],
                content_hash=row[4],
                created_at=row[5],
                updated_at=row[6],
                metadata=metadata
            ))
        
        return entries
    
    def remove_document(self, doc_id: str) -> bool:
        """Remove document and all its index entries."""
        try:
            # Remove index entries first
            self.conn.execute("DELETE FROM index_entries WHERE doc_id = ?", (doc_id,))
            
            # Remove document record
            self.conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
            
            self.conn.commit()
            logger.info(f"Removed document {doc_id[:8]} from registry")
            return True
            
        except Exception as e:
            logger.error(f"Failed to remove document {doc_id}: {e}")
            return False
    
    def remove_index_entries(self, doc_id: str, index_type: IndexType) -> bool:
        """Remove index entries for a specific document and index type."""
        try:
            self.conn.execute("""
                DELETE FROM index_entries WHERE doc_id = ? AND index_type = ?
            """, (doc_id, index_type.value))
            
            # Update document indexing flags
            doc = self.get_document(doc_id)
            if doc:
                if index_type in [IndexType.VECTOR, IndexType.BOTH]:
                    doc.vector_indexed = False
                if index_type in [IndexType.KEYWORD, IndexType.BOTH]:
                    doc.keyword_indexed = False
                
                # Update state based on remaining indexes
                if not doc.vector_indexed and not doc.keyword_indexed:
                    doc.state = DocumentState.NEW.value
                
                self._save_document(doc)
            
            self.conn.commit()
            logger.info(f"Removed {index_type.value} index entries for document {doc_id[:8]}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to remove index entries: {e}")
            return False
    
    def list_documents(
        self,
        state: Optional[DocumentState] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[DocumentRecord]:
        """List documents with optional state filter."""
        query = """
            SELECT doc_id, source, content_hash, size, modified_time, created_at, updated_at,
                   state, vector_indexed, keyword_indexed, chunk_count, error_count, last_error, metadata
            FROM documents
        """
        params = []
        
        if state:
            query += " WHERE state = ?"
            params.append(state.value)
        
        query += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor = self.conn.execute(query, params)
        
        documents = []
        for row in cursor.fetchall():
            documents.append(self._row_to_document(row))
        
        return documents
    
    def get_inconsistent_documents(self) -> List[DocumentRecord]:
        """Find documents with inconsistent index states."""
        # Documents that claim to be indexed but have no index entries
        cursor = self.conn.execute("""
            SELECT d.doc_id, d.source, d.content_hash, d.size, d.modified_time, d.created_at, d.updated_at,
                   d.state, d.vector_indexed, d.keyword_indexed, d.chunk_count, d.error_count, d.last_error, d.metadata
            FROM documents d
            WHERE (d.vector_indexed = 1 AND NOT EXISTS (
                SELECT 1 FROM index_entries ie WHERE ie.doc_id = d.doc_id AND ie.index_type = 'vector'
            )) OR (d.keyword_indexed = 1 AND NOT EXISTS (
                SELECT 1 FROM index_entries ie WHERE ie.doc_id = d.doc_id AND ie.index_type = 'keyword'
            ))
        """)
        
        inconsistent = []
        for row in cursor.fetchall():
            inconsistent.append(self._row_to_document(row))
        
        return inconsistent
    
    def get_orphaned_index_entries(self) -> List[IndexRecord]:
        """Find index entries without corresponding documents."""
        cursor = self.conn.execute("""
            SELECT ie.doc_id, ie.index_type, ie.node_id, ie.chunk_index, ie.content_hash, 
                   ie.created_at, ie.updated_at, ie.metadata
            FROM index_entries ie
            LEFT JOIN documents d ON ie.doc_id = d.doc_id
            WHERE d.doc_id IS NULL
        """)
        
        orphaned = []
        for row in cursor.fetchall():
            metadata = json.loads(row[7]) if row[7] else {}
            orphaned.append(IndexRecord(
                doc_id=row[0],
                index_type=row[1],
                node_id=row[2],
                chunk_index=row[3],
                content_hash=row[4],
                created_at=row[5],
                updated_at=row[6],
                metadata=metadata
            ))
        
        return orphaned
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive registry statistics."""
        # Document statistics by state
        cursor = self.conn.execute("""
            SELECT state, COUNT(*) as count, AVG(chunk_count) as avg_chunks
            FROM documents
            GROUP BY state
        """)
        
        stats_by_state = {}
        total_docs = 0
        
        for row in cursor.fetchall():
            state = row[0]
            count = row[1]
            avg_chunks = row[2] or 0
            
            stats_by_state[state] = {
                "count": count,
                "average_chunks": avg_chunks
            }
            total_docs += count
        
        # Index statistics
        cursor = self.conn.execute("""
            SELECT index_type, COUNT(*) as entry_count, COUNT(DISTINCT doc_id) as doc_count
            FROM index_entries
            GROUP BY index_type
        """)
        
        index_stats = {}
        for row in cursor.fetchall():
            index_type = row[0]
            entry_count = row[1]
            doc_count = row[2]
            
            index_stats[index_type] = {
                "total_entries": entry_count,
                "documents_indexed": doc_count
            }
        
        # Consistency check
        inconsistent_count = len(self.get_inconsistent_documents())
        orphaned_count = len(self.get_orphaned_index_entries())
        
        return {
            "total_documents": total_docs,
            "by_state": stats_by_state,
            "indexes": index_stats,
            "consistency": {
                "inconsistent_documents": inconsistent_count,
                "orphaned_entries": orphaned_count,
                "health_score": max(0, 100 - (inconsistent_count + orphaned_count) * 10)
            },
            "database_path": str(self.storage_path)
        }
    
    def cleanup_orphaned_entries(self) -> int:
        """Remove orphaned index entries."""
        orphaned = self.get_orphaned_index_entries()
        
        if orphaned:
            orphaned_ids = [entry.doc_id for entry in orphaned]
            placeholders = ",".join("?" * len(orphaned_ids))
            
            self.conn.execute(f"""
                DELETE FROM index_entries WHERE doc_id IN ({placeholders})
            """, orphaned_ids)
            
            self.conn.commit()
            logger.info(f"Cleaned up {len(orphaned)} orphaned index entries")
        
        return len(orphaned)
    
    def close(self) -> None:
        """Close database connection."""
        if hasattr(self, 'conn'):
            self.conn.close()
            logger.debug("Document registry database connection closed")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
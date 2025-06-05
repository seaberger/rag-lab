"""
Document Fingerprinting - Phase 1 Implementation

Content fingerprinting and change detection for intelligent document processing.
Tracks document versions to avoid redundant processing and enable updates.
"""

import hashlib
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Add parent directory to path for imports
import sys
sys.path.append(str(Path(__file__).parent.parent))

from utils.common_utils import logger
from utils.config import PipelineConfig


@dataclass
class DocumentFingerprint:
    """Represents a document fingerprint with metadata."""
    source: str
    content_hash: str
    size: int
    modified_time: float
    metadata_hash: str
    created_at: float
    last_seen: float
    doc_id: Optional[str] = None
    processing_status: str = "unknown"


class FingerprintManager:
    """Manages document fingerprints for change detection."""
    
    def __init__(self, config: Optional[PipelineConfig] = None):
        """Initialize fingerprint manager with configuration."""
        self.config = config or PipelineConfig()
        
        # Use configured storage path
        self.storage_path = Path(self.config.fingerprint.storage_path)
        self.retention_days = self.config.fingerprint.retention_days
        self.include_metadata = self.config.fingerprint.include_metadata
        
        # Initialize database
        self._init_database()
        
        logger.info(f"FingerprintManager initialized with storage: {self.storage_path}")
    
    def _init_database(self) -> None:
        """Initialize SQLite database for fingerprint storage."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.conn = sqlite3.connect(str(self.storage_path))
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS fingerprints (
                source TEXT PRIMARY KEY,
                content_hash TEXT NOT NULL,
                size INTEGER NOT NULL,
                modified_time REAL NOT NULL,
                metadata_hash TEXT NOT NULL,
                created_at REAL NOT NULL,
                last_seen REAL NOT NULL,
                doc_id TEXT,
                processing_status TEXT DEFAULT 'unknown'
            )
        """)
        
        # Create index for performance
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_fingerprints_content_hash 
            ON fingerprints(content_hash)
        """)
        
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_fingerprints_last_seen 
            ON fingerprints(last_seen)
        """)
        
        self.conn.commit()
        logger.info("Fingerprint database initialized")
    
    @staticmethod
    def compute_fingerprint(
        source: Union[str, Path], 
        include_metadata: bool = True
    ) -> DocumentFingerprint:
        """Compute fingerprint for a document."""
        source_path = Path(source)
        
        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source}")
        
        # Read file content
        try:
            content = source_path.read_bytes()
            content_hash = hashlib.sha256(content).hexdigest()
        except Exception as e:
            raise Exception(f"Failed to read file {source}: {e}")
        
        # Get file metadata
        stat = source_path.stat()
        size = stat.st_size
        modified_time = stat.st_mtime
        
        # Compute metadata hash if requested
        if include_metadata:
            metadata_parts = [
                str(source_path.name),
                str(size),
                str(modified_time),
                content_hash
            ]
            metadata_hash = hashlib.sha256(
                "|".join(metadata_parts).encode()
            ).hexdigest()
        else:
            metadata_hash = content_hash
        
        current_time = time.time()
        
        return DocumentFingerprint(
            source=str(source_path.resolve()),
            content_hash=content_hash,
            size=size,
            modified_time=modified_time,
            metadata_hash=metadata_hash,
            created_at=current_time,
            last_seen=current_time
        )
    
    def get_fingerprint(self, source: Union[str, Path]) -> Optional[DocumentFingerprint]:
        """Get stored fingerprint for a document."""
        source_key = str(Path(source).resolve())
        
        cursor = self.conn.execute("""
            SELECT source, content_hash, size, modified_time, metadata_hash,
                   created_at, last_seen, doc_id, processing_status
            FROM fingerprints 
            WHERE source = ?
        """, (source_key,))
        
        row = cursor.fetchone()
        if row:
            return DocumentFingerprint(
                source=row[0],
                content_hash=row[1],
                size=row[2],
                modified_time=row[3],
                metadata_hash=row[4],
                created_at=row[5],
                last_seen=row[6],
                doc_id=row[7],
                processing_status=row[8]
            )
        
        return None
    
    def update_fingerprint(
        self, 
        fingerprint: DocumentFingerprint,
        doc_id: Optional[str] = None,
        processing_status: str = "processed"
    ) -> None:
        """Store or update a document fingerprint."""
        fingerprint.last_seen = time.time()
        
        if doc_id:
            fingerprint.doc_id = doc_id
        
        fingerprint.processing_status = processing_status
        
        self.conn.execute("""
            INSERT OR REPLACE INTO fingerprints 
            (source, content_hash, size, modified_time, metadata_hash,
             created_at, last_seen, doc_id, processing_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            fingerprint.source,
            fingerprint.content_hash,
            fingerprint.size,
            fingerprint.modified_time,
            fingerprint.metadata_hash,
            fingerprint.created_at,
            fingerprint.last_seen,
            fingerprint.doc_id,
            fingerprint.processing_status
        ))
        
        self.conn.commit()
        logger.debug(f"Updated fingerprint for {fingerprint.source}")
    
    def has_changed(self, source: Union[str, Path]) -> bool:
        """Check if document has changed since last processing."""
        try:
            # Compute current fingerprint
            current = self.compute_fingerprint(source, self.include_metadata)
            
            # Get stored fingerprint
            stored = self.get_fingerprint(source)
            
            if not stored:
                # New document
                logger.info(f"New document detected: {source}")
                return True
            
            # Update last_seen for existing document
            stored.last_seen = time.time()
            self.update_fingerprint(stored)
            
            # Compare fingerprints
            if current.metadata_hash != stored.metadata_hash:
                logger.info(f"Document changed: {source}")
                logger.debug(f"Hash changed: {stored.metadata_hash[:8]} -> {current.metadata_hash[:8]}")
                return True
            else:
                logger.debug(f"Document unchanged: {source}")
                return False
                
        except Exception as e:
            logger.error(f"Error checking document changes for {source}: {e}")
            # Conservative approach: assume changed if we can't determine
            return True
    
    def get_processing_status(self, source: Union[str, Path]) -> str:
        """Get processing status for a document."""
        fingerprint = self.get_fingerprint(source)
        return fingerprint.processing_status if fingerprint else "unknown"
    
    def mark_processing_status(
        self, 
        source: Union[str, Path], 
        status: str,
        doc_id: Optional[str] = None
    ) -> bool:
        """Mark processing status for a document."""
        try:
            fingerprint = self.get_fingerprint(source)
            
            if not fingerprint:
                # Create new fingerprint
                fingerprint = self.compute_fingerprint(source, self.include_metadata)
            
            fingerprint.processing_status = status
            if doc_id:
                fingerprint.doc_id = doc_id
            
            self.update_fingerprint(fingerprint)
            return True
            
        except Exception as e:
            logger.error(f"Error marking processing status for {source}: {e}")
            return False
    
    def get_document_history(self, source: Union[str, Path]) -> List[Dict[str, Any]]:
        """Get processing history for a document."""
        source_key = str(Path(source).resolve())
        
        cursor = self.conn.execute("""
            SELECT content_hash, size, modified_time, created_at, last_seen,
                   doc_id, processing_status
            FROM fingerprints 
            WHERE source = ?
            ORDER BY created_at DESC
        """, (source_key,))
        
        history = []
        for row in cursor.fetchall():
            history.append({
                "content_hash": row[0],
                "size": row[1],
                "modified_time": row[2],
                "created_at": row[3],
                "last_seen": row[4],
                "doc_id": row[5],
                "processing_status": row[6]
            })
        
        return history
    
    def list_documents(
        self, 
        status_filter: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """List documents with their fingerprint info."""
        query = """
            SELECT source, content_hash, size, modified_time, created_at,
                   last_seen, doc_id, processing_status
            FROM fingerprints
        """
        params = []
        
        if status_filter:
            query += " WHERE processing_status = ?"
            params.append(status_filter)
        
        query += " ORDER BY last_seen DESC LIMIT ?"
        params.append(limit)
        
        cursor = self.conn.execute(query, params)
        
        documents = []
        for row in cursor.fetchall():
            documents.append({
                "source": row[0],
                "content_hash": row[1][:16],  # Truncated for display
                "size": row[2],
                "modified_time": row[3],
                "created_at": row[4],
                "last_seen": row[5],
                "doc_id": row[6],
                "processing_status": row[7]
            })
        
        return documents
    
    def cleanup_old_fingerprints(self, older_than_days: Optional[int] = None) -> int:
        """Clean up fingerprints for documents not seen recently."""
        cutoff_days = older_than_days or self.retention_days
        cutoff_time = time.time() - (cutoff_days * 24 * 60 * 60)
        
        # Get count before deletion
        cursor = self.conn.execute("""
            SELECT COUNT(*) FROM fingerprints WHERE last_seen < ?
        """, (cutoff_time,))
        count = cursor.fetchone()[0]
        
        if count > 0:
            # Delete old fingerprints
            self.conn.execute("""
                DELETE FROM fingerprints WHERE last_seen < ?
            """, (cutoff_time,))
            self.conn.commit()
            
            logger.info(f"Cleaned up {count} old fingerprints (older than {cutoff_days} days)")
        
        return count
    
    def get_stats(self) -> Dict[str, Any]:
        """Get fingerprint database statistics."""
        cursor = self.conn.execute("""
            SELECT 
                COUNT(*) as total_documents,
                COUNT(CASE WHEN processing_status = 'processed' THEN 1 END) as processed,
                COUNT(CASE WHEN processing_status = 'failed' THEN 1 END) as failed,
                COUNT(CASE WHEN processing_status = 'processing' THEN 1 END) as processing,
                AVG(size) as avg_size,
                MIN(created_at) as oldest_fingerprint,
                MAX(last_seen) as newest_fingerprint
            FROM fingerprints
        """)
        
        row = cursor.fetchone()
        
        return {
            "total_documents": row[0],
            "processed": row[1],
            "failed": row[2],
            "processing": row[3],
            "average_size_bytes": int(row[4]) if row[4] else 0,
            "oldest_fingerprint": row[5],
            "newest_fingerprint": row[6],
            "database_path": str(self.storage_path),
            "retention_days": self.retention_days
        }
    
    def close(self) -> None:
        """Close database connection."""
        if hasattr(self, 'conn'):
            self.conn.close()
            logger.debug("Fingerprint database connection closed")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
"""
Enhanced Index Manager with Atomic Operations

Extends the base IndexManager to support distributed transactions
across all storage systems for consistency guarantees.
"""

import hashlib
from pathlib import Path
from typing import Any

from ..storage.keyword_index import BM25Index
from ..utils.common_utils import logger
from ..utils.config import PipelineConfig
from .consistency_checker import ConsistencyChecker, RepairStrategy
from .fingerprint import FingerprintManager
from .index_manager import IndexManager
from .registry import IndexType
from .storage_adapters import (
    FingerprintAdapter,
    KeywordIndexAdapter,
    QdrantAdapter,
    RegistryAdapter,
    StorageArtifactsAdapter,
)
from .transaction_coordinator import OperationType, TransactionCoordinator, TransactionOperation


class AtomicIndexManager(IndexManager):
    """
    Index Manager with atomic operations across all storage systems.

    Provides the same interface as IndexManager but with consistency guarantees
    through distributed transactions.
    """

    def __init__(
        self,
        config: PipelineConfig | None = None,
        registry=None,
        enable_transactions: bool = True,
        transaction_timeout: float = 30.0,
    ):
        """
        Initialize atomic index manager.

        Args:
            config: Pipeline configuration
            registry: Document registry instance
            enable_transactions: Whether to use atomic operations
            transaction_timeout: Timeout for transactions in seconds
        """
        super().__init__(config, registry)

        self.enable_transactions = enable_transactions
        self.transaction_timeout = transaction_timeout

        # Initialize additional components
        self.fingerprint_manager = FingerprintManager(config)
        self.keyword_index = BM25Index(self.keyword_db_path)
        self.storage_dir = Path(config.storage.artifact_path)
        self.storage_dir.mkdir(exist_ok=True)

        if enable_transactions:
            self._init_transaction_support()
            self._init_consistency_checker()

        logger.info(
            f"AtomicIndexManager initialized "
            f"(transactions={'enabled' if enable_transactions else 'disabled'})"
        )

    def _init_transaction_support(self) -> None:
        """Initialize transaction coordinator and adapters"""
        # Create storage system adapters
        self.adapters = {
            "registry": RegistryAdapter(self.registry),
            "qdrant": QdrantAdapter(self.qdrant_client, self.config.qdrant.collection_name),
            "keyword": KeywordIndexAdapter(self.keyword_index),
            "storage": StorageArtifactsAdapter(self.storage_dir),
            "fingerprint": FingerprintAdapter(self.fingerprint_manager),
        }

        # Create transaction coordinator
        self.transaction_coordinator = TransactionCoordinator(
            systems=list(self.adapters.values()), timeout=self.transaction_timeout
        )

        logger.info("Transaction support initialized with 5 storage systems")

    def _init_consistency_checker(self) -> None:
        """Initialize consistency checker"""
        self.consistency_checker = ConsistencyChecker(
            registry=self.registry,
            index_manager=self,
            fingerprint_manager=self.fingerprint_manager,
            storage_dir=str(self.storage_dir),
        )

        logger.info("Consistency checker initialized")

    # Override base methods to add atomic operations

    async def add_document_atomic(
        self,
        doc_id: str,
        nodes: list[Any],
        content: str,
        metadata: dict[str, Any],
        file_path: str,
        index_types: IndexType = IndexType.BOTH,
    ) -> bool:
        """
        Add document with atomic guarantees across all systems.

        This ensures all-or-nothing behavior:
        - Document registry entry
        - Vector embeddings in Qdrant
        - Keyword index entries
        - Storage artifact creation
        - Fingerprint storage

        Args:
            doc_id: Document identifier
            nodes: List of TextNode objects with content
            content: Full document content
            metadata: Document metadata
            file_path: Path to original document
            index_types: Which indexes to populate

        Returns:
            Success status
        """
        if not self.enable_transactions:
            # Fall back to non-atomic operation
            return self.add_document(doc_id, content, metadata, index_types)

        try:
            # Generate fingerprint for the document
            fingerprint = hashlib.sha256(content.encode()).hexdigest()

            # Create storage artifact data
            artifact_data = {
                "doc_id": doc_id,
                "file_path": str(file_path),
                "content": content,
                "metadata": metadata,
                "nodes": [
                    {
                        "node_id": node.node_id,
                        "text": node.text,
                        "metadata": node.metadata,
                        "embedding": node.embedding.tolist()
                        if hasattr(node, "embedding") and node.embedding is not None
                        else None,
                    }
                    for node in nodes
                ],
                "fingerprint": fingerprint,
                "index_types": index_types.value,
            }

            # Create transaction operation
            operation = TransactionOperation(
                operation_type=OperationType.ADD_DOCUMENT,
                doc_id=doc_id,
                data={
                    "nodes": nodes,
                    "content": content,
                    "file_path": file_path,
                    "fingerprint": fingerprint,
                    "artifact_data": artifact_data,
                },
                metadata=metadata,
            )

            # Execute atomic transaction
            success, errors, details = await self.transaction_coordinator.execute_transaction(
                operation
            )

            if success:
                logger.info(f"Successfully added document {doc_id} atomically")
            else:
                logger.error(f"Failed to add document {doc_id} atomically: {errors}")

            return success

        except Exception as e:
            logger.error(f"Atomic add failed for {doc_id}: {e}")
            return False

    async def update_document_atomic(
        self,
        doc_id: str,
        nodes: list[Any],
        content: str,
        metadata: dict[str, Any],
        file_path: str,
        index_types: IndexType = IndexType.BOTH,
    ) -> bool:
        """
        Update document with atomic guarantees.

        Ensures consistent update across all systems or rollback on failure.
        """
        if not self.enable_transactions:
            # Fall back to delete + add
            self.delete_document(doc_id)
            return self.add_document(doc_id, content, metadata, index_types)

        try:
            # Generate new fingerprint
            fingerprint = hashlib.sha256(content.encode()).hexdigest()

            # Create storage artifact data
            artifact_data = {
                "doc_id": doc_id,
                "file_path": str(file_path),
                "content": content,
                "metadata": metadata,
                "nodes": [
                    {
                        "node_id": node.node_id,
                        "text": node.text,
                        "metadata": node.metadata,
                        "embedding": node.embedding.tolist()
                        if hasattr(node, "embedding") and node.embedding is not None
                        else None,
                    }
                    for node in nodes
                ],
                "fingerprint": fingerprint,
                "index_types": index_types.value,
            }

            # Create transaction operation
            operation = TransactionOperation(
                operation_type=OperationType.UPDATE_DOCUMENT,
                doc_id=doc_id,
                data={
                    "nodes": nodes,
                    "content": content,
                    "file_path": file_path,
                    "fingerprint": fingerprint,
                    "artifact_data": artifact_data,
                },
                metadata=metadata,
            )

            # Execute atomic transaction
            success, errors, details = await self.transaction_coordinator.execute_transaction(
                operation
            )

            if success:
                logger.info(f"Successfully updated document {doc_id} atomically")
            else:
                logger.error(f"Failed to update document {doc_id} atomically: {errors}")

            return success

        except Exception as e:
            logger.error(f"Atomic update failed for {doc_id}: {e}")
            return False

    async def delete_document_atomic(self, doc_id: str) -> bool:
        """
        Delete document with atomic guarantees.

        Ensures document is removed from all systems or none.
        """
        if not self.enable_transactions:
            return self.delete_document(doc_id)

        try:
            # Create transaction operation
            operation = TransactionOperation(
                operation_type=OperationType.DELETE_DOCUMENT, doc_id=doc_id, data={}
            )

            # Execute atomic transaction
            success, errors, details = await self.transaction_coordinator.execute_transaction(
                operation
            )

            if success:
                logger.info(f"Successfully deleted document {doc_id} atomically")
            else:
                logger.error(f"Failed to delete document {doc_id} atomically: {errors}")

            return success

        except Exception as e:
            logger.error(f"Atomic delete failed for {doc_id}: {e}")
            return False

    # Consistency checking methods

    async def check_consistency(self, include_orphans: bool = True) -> dict[str, Any]:
        """
        Check consistency across all storage systems.

        Returns:
            Dict with consistency report
        """
        if not self.enable_transactions:
            logger.warning("Consistency checking requires transaction support")
            return {"error": "Transaction support disabled"}

        report = await self.consistency_checker.check_all_documents(include_orphans=include_orphans)

        return report.to_dict()

    async def repair_inconsistencies(
        self, strategy: RepairStrategy = RepairStrategy.TRUST_REGISTRY, dry_run: bool = True
    ) -> dict[str, Any]:
        """
        Repair detected inconsistencies.

        Args:
            strategy: Repair strategy to use
            dry_run: If True, only simulate repairs

        Returns:
            Dict with repair results
        """
        if not self.enable_transactions:
            logger.warning("Repair requires transaction support")
            return {"error": "Transaction support disabled"}

        # First check for inconsistencies
        report = await self.consistency_checker.check_all_documents()

        if report.inconsistent_documents == 0:
            return {
                "message": "No inconsistencies found",
                "total_documents": report.total_documents,
            }

        # Repair inconsistencies
        repair_results = await self.consistency_checker.repair_inconsistencies(
            report, strategy, dry_run
        )

        return {
            "inconsistencies_found": len(report.inconsistencies),
            "repair_attempts": len(repair_results),
            "successful_repairs": sum(1 for r in repair_results if r.success),
            "dry_run": dry_run,
            "strategy": strategy.value,
            "results": [r.to_dict() for r in repair_results],
        }

    # Helper methods for consistency checker

    async def verify_vector_index_state(self, doc_id: str) -> dict[str, Any]:
        """Verify document state in vector index"""
        if not self.qdrant_client:
            return {"exists": False}

        try:
            points = self.qdrant_client.scroll(
                collection_name=self.config.qdrant.collection_name,
                scroll_filter={"must": [{"key": "doc_id", "match": {"value": doc_id}}]},
                limit=1,
            )[0]

            return {"exists": len(points) > 0, "point_count": len(points)}
        except Exception as e:
            logger.error(f"Error verifying vector index state: {e}")
            return {"exists": False, "error": str(e)}

    async def verify_keyword_index_state(self, doc_id: str) -> dict[str, Any]:
        """Verify document state in keyword index"""
        try:
            with self.keyword_conn as conn:
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM keyword_index WHERE doc_id = ?", (doc_id,)
                )
                count = cursor.fetchone()[0]

                return {"exists": count > 0, "chunk_count": count}
        except Exception as e:
            logger.error(f"Error verifying keyword index state: {e}")
            return {"exists": False, "error": str(e)}

    async def delete_from_vector_index(self, doc_id: str) -> bool:
        """Delete document from vector index"""
        if not self.qdrant_client:
            return False

        try:
            self.qdrant_client.delete(
                collection_name=self.config.qdrant.collection_name,
                points_selector={
                    "filter": {"must": [{"key": "doc_id", "match": {"value": doc_id}}]}
                },
            )
            return True
        except Exception as e:
            logger.error(f"Error deleting from vector index: {e}")
            return False

    async def delete_from_keyword_index(self, doc_id: str) -> bool:
        """Delete document from keyword index"""
        try:
            return self.keyword_index.delete_document(doc_id)
        except Exception as e:
            logger.error(f"Error deleting from keyword index: {e}")
            return False

    def get_transaction_log(self) -> list[dict[str, Any]]:
        """Get transaction log for debugging"""
        if not self.enable_transactions:
            return []

        return self.transaction_coordinator.get_transaction_log()

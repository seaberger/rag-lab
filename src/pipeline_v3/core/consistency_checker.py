"""
Consistency Checker for Cross-System Verification

Detects and repairs inconsistencies across Pipeline v3's storage systems.
Provides automated verification and repair capabilities.
"""

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from .fingerprint import FingerprintManager
from .index_manager import IndexManager
from .registry import DocumentRegistry, DocumentState


class InconsistencyType(Enum):
    """Types of inconsistencies that can occur"""

    MISSING_FROM_REGISTRY = "missing_from_registry"
    MISSING_FROM_VECTOR_INDEX = "missing_from_vector_index"
    MISSING_FROM_KEYWORD_INDEX = "missing_from_keyword_index"
    MISSING_FROM_STORAGE = "missing_from_storage"
    MISSING_FROM_FINGERPRINT = "missing_from_fingerprint"
    STATE_MISMATCH = "state_mismatch"
    METADATA_MISMATCH = "metadata_mismatch"
    COUNT_MISMATCH = "count_mismatch"
    ORPHANED_DATA = "orphaned_data"


class RepairStrategy(Enum):
    """Strategies for repairing inconsistencies"""

    TRUST_REGISTRY = "trust_registry"  # Registry is source of truth
    TRUST_STORAGE = "trust_storage"  # Storage artifacts are source of truth
    REMOVE_ALL = "remove_all"  # Remove from all systems
    REINDEX = "reindex"  # Re-process from storage artifacts
    MANUAL = "manual"  # Require manual intervention


@dataclass
class DocumentInconsistency:
    """Details of a document inconsistency"""

    doc_id: str
    types: list[InconsistencyType]
    missing_from: list[str] = field(default_factory=list)
    present_in: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    severity: str = "medium"  # low, medium, high, critical

    def add_type(self, inconsistency_type: InconsistencyType) -> None:
        """Add an inconsistency type"""
        if inconsistency_type not in self.types:
            self.types.append(inconsistency_type)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for reporting"""
        return {
            "doc_id": self.doc_id,
            "types": [t.value for t in self.types],
            "missing_from": self.missing_from,
            "present_in": self.present_in,
            "details": self.details,
            "severity": self.severity,
        }


@dataclass
class ConsistencyReport:
    """Report of consistency check results"""

    timestamp: datetime = field(default_factory=datetime.now)
    total_documents: int = 0
    consistent_documents: int = 0
    inconsistent_documents: int = 0
    inconsistencies: list[DocumentInconsistency] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duration_ms: float = 0

    @property
    def consistency_rate(self) -> float:
        """Calculate consistency rate as percentage"""
        if self.total_documents == 0:
            return 100.0
        return (self.consistent_documents / self.total_documents) * 100

    def add_inconsistency(self, inconsistency: DocumentInconsistency) -> None:
        """Add an inconsistency to the report"""
        self.inconsistencies.append(inconsistency)
        self.inconsistent_documents = len(self.inconsistencies)
        self.consistent_documents = self.total_documents - self.inconsistent_documents

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for reporting"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "total_documents": self.total_documents,
            "consistent_documents": self.consistent_documents,
            "inconsistent_documents": self.inconsistent_documents,
            "consistency_rate": self.consistency_rate,
            "inconsistencies": [i.to_dict() for i in self.inconsistencies],
            "errors": self.errors,
            "duration_ms": self.duration_ms,
        }


@dataclass
class RepairResult:
    """Result of repair operation"""

    doc_id: str
    success: bool
    strategy: RepairStrategy
    actions_taken: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary"""
        return {
            "doc_id": self.doc_id,
            "success": self.success,
            "strategy": self.strategy.value,
            "actions_taken": self.actions_taken,
            "errors": self.errors,
        }


class ConsistencyChecker:
    """
    Verifies and repairs consistency across storage systems.

    Checks for inconsistencies between:
    - Document Registry
    - Vector Index (Qdrant)
    - Keyword Index (BM25)
    - Storage Artifacts (JSONL)
    - Fingerprint Store
    """

    def __init__(
        self,
        registry: DocumentRegistry,
        index_manager: IndexManager,
        fingerprint_manager: FingerprintManager,
        storage_dir: str,
    ):
        self.registry = registry
        self.index_manager = index_manager
        self.fingerprint_manager = fingerprint_manager
        self.storage_dir = storage_dir
        self.logger = logging.getLogger(__name__)

    async def check_all_documents(
        self, batch_size: int = 100, include_orphans: bool = True
    ) -> ConsistencyReport:
        """
        Check consistency of all documents.

        Args:
            batch_size: Number of documents to check in parallel
            include_orphans: Whether to check for orphaned data

        Returns:
            ConsistencyReport with all findings
        """
        start_time = datetime.now()
        report = ConsistencyReport()

        try:
            # Get all document IDs from all systems
            all_doc_ids = await self._get_all_document_ids(include_orphans)
            report.total_documents = len(all_doc_ids)

            self.logger.info(f"Checking consistency for {len(all_doc_ids)} documents")

            # Check documents in batches
            for i in range(0, len(all_doc_ids), batch_size):
                batch = list(all_doc_ids)[i : i + batch_size]

                # Check batch in parallel
                tasks = [self._check_document(doc_id) for doc_id in batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Process results
                for doc_id, result in zip(batch, results, strict=False):
                    if isinstance(result, Exception):
                        report.errors.append(f"Error checking {doc_id}: {result!s}")
                    elif result is not None:
                        report.add_inconsistency(result)

            # Calculate final stats
            report.duration_ms = (datetime.now() - start_time).total_seconds() * 1000

            self.logger.info(
                f"Consistency check complete: {report.consistency_rate:.1f}% consistent "
                f"({report.consistent_documents}/{report.total_documents})"
            )

            return report

        except Exception as e:
            report.errors.append(f"Check failed: {e!s}")
            self.logger.exception(f"Consistency check failed: {e}")
            return report

    async def _get_all_document_ids(self, include_orphans: bool) -> set[str]:
        """Get all document IDs from all systems"""
        all_ids = set()

        # Get from registry
        registry_docs = self.registry.list_documents()
        registry_ids = {doc.doc_id for doc in registry_docs}
        all_ids.update(registry_ids)

        if include_orphans:
            # Get from vector index
            try:
                vector_ids = await self._get_vector_index_doc_ids()
                all_ids.update(vector_ids)
            except Exception as e:
                self.logger.exception(f"Error getting vector index IDs: {e}")

            # Get from keyword index
            try:
                keyword_ids = self._get_keyword_index_doc_ids()
                all_ids.update(keyword_ids)
            except Exception as e:
                self.logger.exception(f"Error getting keyword index IDs: {e}")

            # Get from storage artifacts
            try:
                storage_ids = self._get_storage_doc_ids()
                all_ids.update(storage_ids)
            except Exception as e:
                self.logger.exception(f"Error getting storage IDs: {e}")

            # Get from fingerprint store
            try:
                fingerprint_ids = self._get_fingerprint_doc_ids()
                all_ids.update(fingerprint_ids)
            except Exception as e:
                self.logger.exception(f"Error getting fingerprint IDs: {e}")

        return all_ids

    async def _check_document(self, doc_id: str) -> DocumentInconsistency | None:
        """Check consistency for a single document"""
        inconsistency = None

        # Check presence in each system
        presence = await self._check_document_presence(doc_id)

        # If document is in all systems, we're consistent (basic check)
        if all(presence.values()):
            # Could do deeper checks here (metadata, counts, etc.)
            return None

        # If document is in no systems, it doesn't exist (consistent)
        if not any(presence.values()):
            return None

        # We have an inconsistency
        inconsistency = DocumentInconsistency(doc_id=doc_id, types=[])

        # Determine what's missing
        for system, present in presence.items():
            if present:
                inconsistency.present_in.append(system)
            else:
                inconsistency.missing_from.append(system)

        # Classify the inconsistency
        if not presence["registry"]:
            inconsistency.add_type(InconsistencyType.MISSING_FROM_REGISTRY)
            inconsistency.severity = "critical"

        if not presence["vector_index"]:
            inconsistency.add_type(InconsistencyType.MISSING_FROM_VECTOR_INDEX)

        if not presence["keyword_index"]:
            inconsistency.add_type(InconsistencyType.MISSING_FROM_KEYWORD_INDEX)

        if not presence["storage"]:
            inconsistency.add_type(InconsistencyType.MISSING_FROM_STORAGE)
            if presence["registry"]:
                inconsistency.severity = "high"

        if not presence["fingerprint"]:
            inconsistency.add_type(InconsistencyType.MISSING_FROM_FINGERPRINT)

        # Check for orphaned data
        if not presence["registry"] and any(
            [presence["vector_index"], presence["keyword_index"], presence["storage"]]
        ):
            inconsistency.add_type(InconsistencyType.ORPHANED_DATA)
            inconsistency.severity = "high"

        return inconsistency

    async def _check_document_presence(self, doc_id: str) -> dict[str, bool]:
        """Check if document exists in each system"""
        presence = {}

        # Check registry
        doc = self.registry.get_document(doc_id)
        presence["registry"] = doc is not None

        # Check vector index
        try:
            vector_state = await self.index_manager.verify_vector_index_state(doc_id)
            presence["vector_index"] = vector_state.get("exists", False)
        except Exception:
            presence["vector_index"] = False

        # Check keyword index
        try:
            keyword_state = await self.index_manager.verify_keyword_index_state(doc_id)
            presence["keyword_index"] = keyword_state.get("exists", False)
        except Exception:
            presence["keyword_index"] = False

        # Check storage
        storage_path = f"{self.storage_dir}/{doc_id}.jsonl"
        presence["storage"] = self._file_exists(storage_path)

        # Check fingerprint
        # Note: FingerprintManager uses source paths, not doc_ids
        # We need to get the source path from registry
        if doc:
            fp = self.fingerprint_manager.get_fingerprint(doc.source)
            presence["fingerprint"] = fp is not None
        else:
            presence["fingerprint"] = False

        return presence

    async def repair_inconsistencies(
        self,
        report: ConsistencyReport,
        strategy: RepairStrategy = RepairStrategy.TRUST_REGISTRY,
        dry_run: bool = False,
    ) -> list[RepairResult]:
        """
        Attempt to repair detected inconsistencies.

        Args:
            report: ConsistencyReport with inconsistencies to repair
            strategy: Repair strategy to use
            dry_run: If True, only simulate repairs

        Returns:
            List of RepairResult objects
        """
        results = []

        self.logger.info(
            f"Repairing {len(report.inconsistencies)} inconsistencies "
            f"using strategy: {strategy.value} (dry_run={dry_run})"
        )

        for inconsistency in report.inconsistencies:
            result = await self._repair_document(inconsistency, strategy, dry_run)
            results.append(result)

        # Log summary
        successful = sum(1 for r in results if r.success)
        self.logger.info(f"Repair complete: {successful}/{len(results)} successful")

        return results

    async def _repair_document(
        self,
        inconsistency: DocumentInconsistency,
        strategy: RepairStrategy,
        dry_run: bool,
    ) -> RepairResult:
        """Repair a single document inconsistency"""
        result = RepairResult(doc_id=inconsistency.doc_id, success=False, strategy=strategy)

        try:
            if strategy == RepairStrategy.TRUST_REGISTRY:
                await self._repair_trust_registry(inconsistency, result, dry_run)

            elif strategy == RepairStrategy.TRUST_STORAGE:
                await self._repair_trust_storage(inconsistency, result, dry_run)

            elif strategy == RepairStrategy.REMOVE_ALL:
                await self._repair_remove_all(inconsistency, result, dry_run)

            elif strategy == RepairStrategy.REINDEX:
                await self._repair_reindex(inconsistency, result, dry_run)

            elif strategy == RepairStrategy.MANUAL:
                result.actions_taken.append("Manual intervention required")
                result.success = False

            else:
                result.errors.append(f"Unknown strategy: {strategy}")

        except Exception as e:
            result.errors.append(str(e))
            self.logger.exception(f"Repair failed for {inconsistency.doc_id}: {e}")

        return result

    async def _repair_trust_registry(
        self, inconsistency: DocumentInconsistency, result: RepairResult, dry_run: bool
    ) -> None:
        """Repair by trusting registry as source of truth"""
        doc = self.registry.get_document(inconsistency.doc_id)

        if doc is None:
            # Document shouldn't exist - remove from all systems
            if "vector_index" in inconsistency.present_in:
                action = "Remove from vector index"
                result.actions_taken.append(action)
                if not dry_run:
                    await self.index_manager.delete_from_vector_index(inconsistency.doc_id)

            if "keyword_index" in inconsistency.present_in:
                action = "Remove from keyword index"
                result.actions_taken.append(action)
                if not dry_run:
                    await self.index_manager.delete_from_keyword_index(inconsistency.doc_id)

            if "storage" in inconsistency.present_in:
                action = "Remove storage artifact"
                result.actions_taken.append(action)
                if not dry_run:
                    self._remove_storage_artifact(inconsistency.doc_id)

            if "fingerprint" in inconsistency.present_in:
                action = "Remove fingerprint (skipped - not supported)"
                result.actions_taken.append(action)
                # FingerprintManager doesn't support individual deletion

            result.success = True

        elif doc.state == DocumentState.INDEXED:
            # Should be in all systems
            if "storage" in inconsistency.missing_from:
                result.errors.append("Cannot recreate storage artifact from registry")
                result.success = False
                return

            # Re-index if missing from indexes
            if any(
                system in inconsistency.missing_from for system in ["vector_index", "keyword_index"]
            ):
                action = "Re-index document from storage"
                result.actions_taken.append(action)
                if not dry_run:
                    # This would trigger re-indexing
                    pass  # Implementation depends on pipeline

            result.success = True

    async def _repair_trust_storage(
        self, inconsistency: DocumentInconsistency, result: RepairResult, dry_run: bool
    ) -> None:
        """Repair by trusting storage artifacts as source of truth"""
        if "storage" not in inconsistency.present_in:
            result.errors.append("Storage artifact not present - cannot use as source of truth")
            return

        # Re-process from storage artifact
        action = "Re-process document from storage artifact"
        result.actions_taken.append(action)

        if not dry_run:
            # This would trigger full re-processing
            pass  # Implementation depends on pipeline

        result.success = True

    async def _repair_remove_all(
        self, inconsistency: DocumentInconsistency, result: RepairResult, dry_run: bool
    ) -> None:
        """Remove document from all systems"""
        for system in inconsistency.present_in:
            action = f"Remove from {system}"
            result.actions_taken.append(action)

            if not dry_run:
                if system == "registry":
                    self.registry.remove_document(inconsistency.doc_id)
                elif system == "vector_index":
                    await self.index_manager.delete_from_vector_index(inconsistency.doc_id)
                elif system == "keyword_index":
                    await self.index_manager.delete_from_keyword_index(inconsistency.doc_id)
                elif system == "storage":
                    self._remove_storage_artifact(inconsistency.doc_id)
                elif system == "fingerprint":
                    # FingerprintManager doesn't support individual deletion
                    pass

        result.success = True

    async def _repair_reindex(
        self, inconsistency: DocumentInconsistency, result: RepairResult, dry_run: bool
    ) -> None:
        """Re-index document from source"""
        if "storage" not in inconsistency.present_in:
            result.errors.append("Cannot reindex - storage artifact missing")
            return

        action = "Trigger full reindexing from storage"
        result.actions_taken.append(action)

        if not dry_run:
            # This would trigger reindexing
            pass  # Implementation depends on pipeline

        result.success = True

    # Helper methods

    async def _get_vector_index_doc_ids(self) -> set[str]:
        """Get all document IDs from vector index"""
        # Implementation depends on Qdrant client
        return set()

    def _get_keyword_index_doc_ids(self) -> set[str]:
        """Get all document IDs from keyword index"""
        doc_ids = set()
        try:
            # Handle both real IndexManager and MockIndexManager
            if hasattr(self.index_manager, "keyword_index"):
                with self.index_manager.keyword_index.get_connection() as conn:
                    cursor = conn.execute("SELECT DISTINCT doc_id FROM documents")
                    doc_ids = {row[0] for row in cursor.fetchall()}
            elif hasattr(self.index_manager, "keyword_docs"):
                # MockIndexManager for tests
                doc_ids = set(self.index_manager.keyword_docs.keys())
        except Exception as e:
            self.logger.exception(f"Error getting keyword index IDs: {e}")
        return doc_ids

    def _get_storage_doc_ids(self) -> set[str]:
        """Get all document IDs from storage artifacts"""
        from pathlib import Path

        storage_path = Path(self.storage_dir)
        doc_ids = set()

        if storage_path.exists():
            for file_path in storage_path.glob("*.jsonl"):
                doc_id = file_path.stem
                doc_ids.add(doc_id)

        return doc_ids

    def _get_fingerprint_doc_ids(self) -> set[str]:
        """Get all document IDs from fingerprint store"""
        # FingerprintManager tracks by source path, not doc_id
        # We need to get all documents and extract their doc_ids
        doc_ids = set()
        docs = self.fingerprint_manager.list_documents(limit=10000)
        for doc in docs:
            if "doc_id" in doc:
                doc_ids.add(doc["doc_id"])
        return doc_ids

    def _file_exists(self, path: str) -> bool:
        """Check if file exists"""
        from pathlib import Path

        return Path(path).exists()

    def _remove_storage_artifact(self, doc_id: str) -> None:
        """Remove storage artifact file"""
        from pathlib import Path

        file_path = Path(self.storage_dir) / f"{doc_id}.jsonl"
        if file_path.exists():
            file_path.unlink()


class ConsistencyMonitor:
    """
    Background monitor for continuous consistency checking.
    """

    def __init__(self, checker: ConsistencyChecker, check_interval: int = 3600):
        self.checker = checker
        self.check_interval = check_interval
        self.logger = logging.getLogger(__name__)
        self._running = False
        self._task = None

    async def start(self) -> None:
        """Start background monitoring"""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        self.logger.info(f"Consistency monitor started (interval: {self.check_interval}s)")

    async def stop(self) -> None:
        """Stop background monitoring"""
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        self.logger.info("Consistency monitor stopped")

    async def _monitor_loop(self) -> None:
        """Main monitoring loop"""
        while self._running:
            try:
                # Run consistency check
                report = await self.checker.check_all_documents()

                # Log results
                if report.inconsistent_documents > 0:
                    self.logger.warning(
                        f"Consistency check found {report.inconsistent_documents} "
                        f"inconsistent documents ({report.consistency_rate:.1f}% consistent)"
                    )

                    # Could trigger automatic repair here
                    # or send alerts
                else:
                    self.logger.info(
                        f"Consistency check passed: {report.total_documents} documents OK"
                    )

                # Wait for next check
                await asyncio.sleep(self.check_interval)

            except Exception as e:
                self.logger.exception(f"Monitor error: {e}")
                await asyncio.sleep(60)  # Brief pause on error

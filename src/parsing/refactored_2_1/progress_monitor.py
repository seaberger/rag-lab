"""
Progress monitoring and basic metrics collection.
"""

import time
from datetime import datetime
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from collections import defaultdict
import json


@dataclass
class DocumentStats:
    """Statistics for a single document."""

    doc_id: str
    source: str
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    chunks: int = 0
    size_bytes: int = 0
    cached: bool = False
    error: Optional[str] = None
    stages: Dict[str, float] = field(default_factory=dict)


class ProgressMonitor:
    """Track progress and collect metrics."""

    def __init__(self, callback: Optional[Callable] = None):
        self.stats: Dict[str, DocumentStats] = {}
        self.global_stats = {
            "total_docs": 0,
            "processed_docs": 0,
            "failed_docs": 0,
            "total_chunks": 0,
            "total_bytes": 0,
            "cache_hits": 0,
            "start_time": time.time(),
        }
        self.stage_times = defaultdict(list)
        self.callback = callback

    def start_document(self, doc_id: str, source: str, size_bytes: int = 0):
        """Mark document processing start."""
        self.stats[doc_id] = DocumentStats(
            doc_id=doc_id, source=source, size_bytes=size_bytes
        )
        self.global_stats["total_docs"] += 1
        self.global_stats["total_bytes"] += size_bytes

        if self.callback:
            self.callback(
                "document_start",
                {"doc_id": doc_id, "source": source, "progress": self.get_progress()},
            )

    def update_stage(self, doc_id: str, stage: str, duration: Optional[float] = None):
        """Update processing stage."""
        if doc_id in self.stats:
            self.stats[doc_id].stages[stage] = (
                duration or time.time() - self.stats[doc_id].start_time
            )
            self.stage_times[stage].append(self.stats[doc_id].stages[stage])

            if self.callback:
                self.callback(
                    "stage_update",
                    {
                        "doc_id": doc_id,
                        "stage": stage,
                        "duration": self.stats[doc_id].stages[stage],
                    },
                )

    def complete_document(self, doc_id: str, chunks: int = 0, cached: bool = False):
        """Mark document as completed."""
        if doc_id in self.stats:
            self.stats[doc_id].end_time = time.time()
            self.stats[doc_id].chunks = chunks
            self.stats[doc_id].cached = cached

            self.global_stats["processed_docs"] += 1
            self.global_stats["total_chunks"] += chunks
            if cached:
                self.global_stats["cache_hits"] += 1

            if self.callback:
                self.callback(
                    "document_complete",
                    {
                        "doc_id": doc_id,
                        "duration": self.stats[doc_id].end_time
                        - self.stats[doc_id].start_time,
                        "chunks": chunks,
                        "cached": cached,
                    },
                )

    def fail_document(self, doc_id: str, error: str):
        """Mark document as failed."""
        if doc_id in self.stats:
            self.stats[doc_id].end_time = time.time()
            self.stats[doc_id].error = error

            self.global_stats["failed_docs"] += 1

            if self.callback:
                self.callback("document_failed", {"doc_id": doc_id, "error": error})

    def get_progress(self) -> Dict[str, Any]:
        """Get current progress statistics."""
        elapsed = time.time() - self.global_stats["start_time"]
        processed = self.global_stats["processed_docs"]
        total = self.global_stats["total_docs"]

        return {
            "processed": processed,
            "total": total,
            "failed": self.global_stats["failed_docs"],
            "percentage": (processed / total * 100) if total > 0 else 0,
            "elapsed_seconds": elapsed,
            "rate_per_minute": (processed / elapsed * 60) if elapsed > 0 else 0,
            "eta_seconds": (elapsed / processed * (total - processed))
            if processed > 0
            else None,
            "cache_hit_rate": (self.global_stats["cache_hits"] / processed)
            if processed > 0
            else 0,
        }

    def get_summary(self) -> Dict[str, Any]:
        """Get final summary statistics."""
        summary = {
            **self.global_stats,
            "elapsed_time": time.time() - self.global_stats["start_time"],
            "average_doc_time": sum(
                s.end_time - s.start_time for s in self.stats.values() if s.end_time
            )
            / max(1, self.global_stats["processed_docs"]),
            "stage_averages": {
                stage: sum(times) / len(times)
                for stage, times in self.stage_times.items()
                if times
            },
        }
        return summary

    def save_report(self, filepath: str = "pipeline_report.json"):
        """Save detailed report to file."""
        report = {
            "summary": self.get_summary(),
            "documents": [
                {
                    "doc_id": stats.doc_id,
                    "source": stats.source,
                    "duration": stats.end_time - stats.start_time
                    if stats.end_time
                    else None,
                    "chunks": stats.chunks,
                    "cached": stats.cached,
                    "error": stats.error,
                    "stages": stats.stages,
                }
                for stats in self.stats.values()
            ],
            "timestamp": datetime.now().isoformat(),
        }

        with open(filepath, "w") as f:
            json.dump(report, f, indent=2)

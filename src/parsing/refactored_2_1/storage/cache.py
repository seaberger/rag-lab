"""
Simple cache manager for parsed documents.
"""

import json
# import hashlib # Not directly used in this file, but hashes are passed in
import shutil # Not used in the current snippet, consider removing if not needed elsewhere in this file
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

import lz4.frame

# FIXME: logger should be imported, e.g., from ..utils.common_utils import logger
# from ..utils.common_utils import logger # Placeholder if you have a central logger
class PrintLogger: # Basic logger placeholder if no central one is set up yet
    def error(self, msg): print(f"ERROR: {msg}")
    def warning(self, msg): print(f"WARNING: {msg}")
    def info(self, msg): print(f"INFO: {msg}")
logger = PrintLogger()

# FIXME: Consider using PipelineConfig for cache_dir, ttl_days, compress
# from ..utils.config import PipelineConfig

class CacheManager:
    """Simple disk-based cache with optional compression."""

    def __init__(
        self, cache_dir: str = "./cache", ttl_days: int = 7, compress: bool = True
        # config: Optional[PipelineConfig] = None # Example: pass config
    ):
        # FIXME: These should come from config
        # if config:
        #     self.cache_dir = Path(config.cache.directory)
        #     self.ttl = timedelta(days=config.cache.ttl_days)
        #     self.compress = config.cache.compress
        # else:
        self.cache_dir = Path(cache_dir) # Default or from param
        self.cache_dir.mkdir(exist_ok=True)
        self.ttl = timedelta(days=ttl_days)
        self.compress = compress
        self.stats = {"hits": 0, "misses": 0, "errors": 0}

    def _get_cache_key(self, doc_hash: str, prompt_hash: str) -> str:
        """Generate cache key from document and prompt."""
        return f"{doc_hash[:8]}_{prompt_hash[:8]}"

    def _get_cache_path(self, cache_key: str) -> Path:
        """Get path for cached file."""
        ext = ".json.lz4" if self.compress else ".json"
        return self.cache_dir / f"{cache_key}{ext}"

    def get(self, doc_hash: str, prompt_hash: str) -> Optional[Dict[str, Any]]:
        """Retrieve from cache if exists and not expired."""
        cache_key = self._get_cache_key(doc_hash, prompt_hash)
        cache_path = self._get_cache_path(cache_key)

        if not cache_path.exists():
            self.stats["misses"] += 1
            return None

        # Check expiry
        mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
        if datetime.now() - mtime > self.ttl:
            cache_path.unlink()  # Remove expired
            self.stats["misses"] += 1
            return None

        try:
            if self.compress:
                with lz4.frame.open(cache_path, "rb") as f:
                    data = json.loads(f.read())
            else:
                with open(cache_path, "r") as f:
                    data = json.load(f)

            self.stats["hits"] += 1
            return data

        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"Cache read error: {e}")
            return None

    def put(self, doc_hash: str, prompt_hash: str, data: Dict[str, Any]) -> bool:
        """Store in cache."""
        cache_key = self._get_cache_key(doc_hash, prompt_hash)
        cache_path = self._get_cache_path(cache_key)

        try:
            if self.compress:
                with lz4.frame.open(cache_path, "wb") as f:
                    f.write(json.dumps(data).encode())
            else:
                with open(cache_path, "w") as f:
                    json.dump(data, f)
            return True

        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"Cache write error: {e}")
            return False

    def clear(self, older_than_days: Optional[int] = None):
        """Clear cache, optionally only items older than N days."""
        count = 0
        for cache_file in self.cache_dir.glob("*.json*"):
            if older_than_days:
                mtime = datetime.fromtimestamp(cache_file.stat().st_mtime)
                if datetime.now() - mtime < timedelta(days=older_than_days):
                    continue
            cache_file.unlink()
            count += 1
        return count

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_size = sum(f.stat().st_size for f in self.cache_dir.glob("*.json*"))
        return {
            **self.stats,
            "hit_rate": self.stats["hits"]
            / max(1, self.stats["hits"] + self.stats["misses"]),
            "cache_size_mb": total_size / 1024 / 1024,
            "cache_files": len(list(self.cache_dir.glob("*.json*"))),
        }

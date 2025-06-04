#!/usr/bin/env python3
"""
Cache management utility for the datasheet ingestion pipeline.
Provides programmatic and CLI access to cache clearing operations.
"""

import argparse
import shutil
import sys
from pathlib import Path
from typing import List, Optional

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from utils.config import PipelineConfig
    from utils.common_utils import logger
except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure you're running from the correct directory")
    sys.exit(1)


class CacheCleaner:
    """Utility to clear various cache and storage components."""
    
    def __init__(self, config_file: str = "config.yaml"):
        """Initialize with configuration."""
        try:
            self.config = PipelineConfig.from_yaml(config_file)
        except Exception as e:
            logger.warning(f"Could not load config from {config_file}: {e}")
            logger.info("Using default cache locations")
            self.config = None
    
    def get_cache_locations(self) -> dict:
        """Get all cache and storage locations."""
        if self.config:
            locations = {
                "api_cache": Path(self.config.cache.directory),
                "storage_artifacts": Path(self.config.storage.base_dir),
                "vector_db": Path(self.config.qdrant.path),
                "keyword_index": Path(self.config.storage.keyword_db_path),
                "processing_reports": Path("processing_report.json"),
                "pipeline_logs": Path("pipeline.log")
            }
        else:
            # Default locations when config is not available
            locations = {
                "api_cache": Path("./cache"),
                "storage_artifacts": Path("./storage_data"),
                "vector_db": Path("./qdrant_data"),
                "keyword_index": Path("./keyword_index.db"),
                "processing_reports": Path("processing_report.json"),
                "pipeline_logs": Path("pipeline.log")
            }
        
        return locations
    
    def check_cache_status(self) -> dict:
        """Check the status and size of all cache locations."""
        locations = self.get_cache_locations()
        status = {}
        
        for name, path in locations.items():
            if path.exists():
                if path.is_dir():
                    try:
                        files = list(path.rglob("*"))
                        total_files = len([f for f in files if f.is_file()])
                        total_size = sum(f.stat().st_size for f in files if f.is_file())
                        status[name] = {
                            "exists": True,
                            "type": "directory",
                            "files": total_files,
                            "size_mb": round(total_size / (1024*1024), 2)
                        }
                    except PermissionError:
                        status[name] = {"exists": True, "type": "directory", "error": "Permission denied"}
                else:
                    try:
                        size = path.stat().st_size
                        status[name] = {
                            "exists": True,
                            "type": "file",
                            "size_mb": round(size / (1024*1024), 2)
                        }
                    except PermissionError:
                        status[name] = {"exists": True, "type": "file", "error": "Permission denied"}
            else:
                status[name] = {"exists": False}
        
        return status
    
    def clear_api_cache(self) -> bool:
        """Clear API response cache (LZ4 compressed JSON files)."""
        locations = self.get_cache_locations()
        cache_dir = locations["api_cache"]
        
        try:
            if cache_dir.exists():
                shutil.rmtree(cache_dir)
                logger.info(f"✅ Cleared API cache: {cache_dir}")
                return True
            else:
                logger.info(f"API cache directory doesn't exist: {cache_dir}")
                return True
        except Exception as e:
            logger.error(f"❌ Failed to clear API cache: {e}")
            return False
    
    def clear_storage_artifacts(self) -> bool:
        """Clear document artifacts (JSONL files)."""
        locations = self.get_cache_locations()
        storage_dir = locations["storage_artifacts"]
        
        try:
            if storage_dir.exists():
                shutil.rmtree(storage_dir)
                logger.info(f"✅ Cleared storage artifacts: {storage_dir}")
                return True
            else:
                logger.info(f"Storage directory doesn't exist: {storage_dir}")
                return True
        except Exception as e:
            logger.error(f"❌ Failed to clear storage artifacts: {e}")
            return False
    
    def clear_vector_database(self) -> bool:
        """Clear Qdrant vector database."""
        locations = self.get_cache_locations()
        vector_db_dir = locations["vector_db"]
        
        try:
            if vector_db_dir.exists():
                shutil.rmtree(vector_db_dir)
                logger.info(f"✅ Cleared vector database: {vector_db_dir}")
                return True
            else:
                logger.info(f"Vector database doesn't exist: {vector_db_dir}")
                return True
        except Exception as e:
            logger.error(f"❌ Failed to clear vector database: {e}")
            return False
    
    def clear_keyword_index(self) -> bool:
        """Clear BM25 keyword index."""
        locations = self.get_cache_locations()
        keyword_db = locations["keyword_index"]
        
        try:
            if keyword_db.exists():
                keyword_db.unlink()
                logger.info(f"✅ Cleared keyword index: {keyword_db}")
                return True
            else:
                logger.info(f"Keyword index doesn't exist: {keyword_db}")
                return True
        except Exception as e:
            logger.error(f"❌ Failed to clear keyword index: {e}")
            return False
    
    def clear_logs_and_reports(self) -> bool:
        """Clear processing reports and logs."""
        locations = self.get_cache_locations()
        success = True
        
        for name in ["processing_reports", "pipeline_logs"]:
            file_path = locations[name]
            try:
                if file_path.exists():
                    file_path.unlink()
                    logger.info(f"✅ Cleared {name}: {file_path}")
            except Exception as e:
                logger.error(f"❌ Failed to clear {name}: {e}")
                success = False
        
        return success
    
    def clear_all(self) -> bool:
        """Clear all cache and storage components."""
        logger.info("🧹 Clearing all cache and storage components...")
        
        operations = [
            ("API Cache", self.clear_api_cache),
            ("Storage Artifacts", self.clear_storage_artifacts),
            ("Vector Database", self.clear_vector_database),
            ("Keyword Index", self.clear_keyword_index),
            ("Logs and Reports", self.clear_logs_and_reports)
        ]
        
        all_success = True
        for name, operation in operations:
            logger.info(f"Clearing {name}...")
            success = operation()
            if not success:
                all_success = False
        
        if all_success:
            logger.info("✅ All cache components cleared successfully!")
        else:
            logger.warning("⚠️ Some cache clearing operations failed")
        
        return all_success
    
    def selective_clear(self, components: List[str]) -> bool:
        """Clear specific cache components."""
        component_map = {
            "api": self.clear_api_cache,
            "cache": self.clear_api_cache,  # alias
            "storage": self.clear_storage_artifacts,
            "artifacts": self.clear_storage_artifacts,  # alias
            "vector": self.clear_vector_database,
            "qdrant": self.clear_vector_database,  # alias
            "keyword": self.clear_keyword_index,
            "bm25": self.clear_keyword_index,  # alias
            "logs": self.clear_logs_and_reports,
            "reports": self.clear_logs_and_reports,  # alias
        }
        
        all_success = True
        for component in components:
            component_lower = component.lower()
            if component_lower in component_map:
                logger.info(f"Clearing {component}...")
                success = component_map[component_lower]()
                if not success:
                    all_success = False
            else:
                logger.error(f"❌ Unknown component: {component}")
                logger.info(f"Available components: {', '.join(component_map.keys())}")
                all_success = False
        
        return all_success


def main():
    """CLI interface for cache management."""
    parser = argparse.ArgumentParser(
        description="Cache management utility for datasheet ingestion pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cache_manager.py --status                    # Check cache status
  python cache_manager.py --clear-all                 # Clear everything
  python cache_manager.py --clear api storage         # Clear specific components
  python cache_manager.py --clear vector keyword      # Clear vector DB and keyword index
  
Available components for selective clearing:
  api, cache      - API response cache (LZ4 files)
  storage         - Document artifacts (JSONL files)  
  vector, qdrant  - Vector database
  keyword, bm25   - Keyword search index
  logs, reports   - Processing logs and reports
        """
    )
    
    parser.add_argument(
        "--config", 
        default="config.yaml",
        help="Configuration file path (default: config.yaml)"
    )
    parser.add_argument(
        "--status", 
        action="store_true",
        help="Show cache status and sizes"
    )
    parser.add_argument(
        "--clear-all", 
        action="store_true",
        help="Clear all cache and storage components"
    )
    parser.add_argument(
        "--clear", 
        nargs="+",
        help="Clear specific components (see examples below)"
    )
    parser.add_argument(
        "--force", 
        action="store_true",
        help="Skip confirmation prompts"
    )
    
    args = parser.parse_args()
    
    # Initialize cache cleaner
    cleaner = CacheCleaner(args.config)
    
    if args.status:
        print("📊 Cache Status Report")
        print("=" * 50)
        status = cleaner.check_cache_status()
        locations = cleaner.get_cache_locations()
        
        for name, info in status.items():
            location = locations[name]
            print(f"\n{name.upper().replace('_', ' ')}:")
            print(f"  Location: {location}")
            
            if info["exists"]:
                if "error" in info:
                    print(f"  Status: ❌ {info['error']}")
                elif info["type"] == "directory":
                    print(f"  Status: ✅ {info['files']} files, {info['size_mb']} MB")
                else:
                    print(f"  Status: ✅ {info['size_mb']} MB")
            else:
                print(f"  Status: 📭 Not found")
        
        return
    
    if args.clear_all:
        if not args.force:
            print("⚠️  This will clear ALL cache and storage components:")
            locations = cleaner.get_cache_locations()
            for name, path in locations.items():
                print(f"  - {name}: {path}")
            
            response = input("\nProceed? [y/N]: ").strip().lower()
            if response != 'y':
                print("Cancelled.")
                return
        
        success = cleaner.clear_all()
        sys.exit(0 if success else 1)
    
    if args.clear:
        if not args.force:
            print(f"⚠️  This will clear the following components: {', '.join(args.clear)}")
            response = input("Proceed? [y/N]: ").strip().lower()
            if response != 'y':
                print("Cancelled.")
                return
        
        success = cleaner.selective_clear(args.clear)
        sys.exit(0 if success else 1)
    
    # If no action specified, show help
    parser.print_help()


if __name__ == "__main__":
    main()
"""
Resource cleanup utilities for Pipeline v3

Provides context managers and cleanup functions for proper resource management.
"""

import atexit
import logging
import tempfile
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

# Global registry of temporary files to clean up
_temp_files: set[Path] = set()
_temp_dirs: set[Path] = set()


def register_temp_file(path: Path) -> None:
    """Register a temporary file for cleanup on exit."""
    _temp_files.add(path)


def register_temp_dir(path: Path) -> None:
    """Register a temporary directory for cleanup on exit."""
    _temp_dirs.add(path)


def cleanup_temp_resources() -> None:
    """Clean up all registered temporary resources."""
    # Clean up files
    for temp_file in _temp_files:
        try:
            if temp_file.exists():
                temp_file.unlink()
                logger.debug(f"Cleaned up temporary file: {temp_file}")
        except Exception as e:
            logger.warning(f"Failed to clean up temporary file {temp_file}: {e}")

    # Clean up directories
    for temp_dir in _temp_dirs:
        try:
            if temp_dir.exists():
                import shutil

                shutil.rmtree(temp_dir)
                logger.debug(f"Cleaned up temporary directory: {temp_dir}")
        except Exception as e:
            logger.warning(f"Failed to clean up temporary directory {temp_dir}: {e}")

    _temp_files.clear()
    _temp_dirs.clear()


@contextmanager
def temporary_file(suffix: str | None = None, prefix: str | None = None, dir: Path | None = None):
    """
    Context manager for creating and cleaning up temporary files.

    Args:
        suffix: File suffix (e.g., '.pdf')
        prefix: File prefix (e.g., 'download_')
        dir: Directory to create file in (defaults to system temp)

    Yields:
        Path to the temporary file
    """
    temp_file = None
    try:
        # Create temporary file
        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=suffix, prefix=prefix, dir=dir, delete=False
        ) as tf:
            temp_file = Path(tf.name)
            register_temp_file(temp_file)

        yield temp_file

    finally:
        # Clean up if file still exists
        if temp_file and temp_file.exists():
            try:
                temp_file.unlink()
                _temp_files.discard(temp_file)
            except Exception as e:
                logger.warning(f"Failed to clean up temporary file {temp_file}: {e}")


@contextmanager
def temporary_directory(
    suffix: str | None = None, prefix: str | None = None, dir: Path | None = None
):
    """
    Context manager for creating and cleaning up temporary directories.

    Args:
        suffix: Directory suffix
        prefix: Directory prefix (e.g., 'processing_')
        dir: Parent directory (defaults to system temp)

    Yields:
        Path to the temporary directory
    """
    temp_dir = Path(tempfile.mkdtemp(suffix=suffix, prefix=prefix, dir=dir))
    register_temp_dir(temp_dir)

    try:
        yield temp_dir
    finally:
        # Clean up directory
        try:
            import shutil

            shutil.rmtree(temp_dir)
            _temp_dirs.discard(temp_dir)
        except Exception as e:
            logger.warning(f"Failed to clean up temporary directory {temp_dir}: {e}")


# Register cleanup function to run on exit
atexit.register(cleanup_temp_resources)


class ResourceManager:
    """
    Manages cleanup of various resources including database connections.
    """

    def __init__(self):
        self.connections: list = []
        self.temp_files: list[Path] = []
        self.handlers: list = []

    def register_connection(self, connection) -> None:
        """Register a database connection for cleanup."""
        self.connections.append(connection)

    def register_temp_file(self, path: Path) -> None:
        """Register a temporary file for cleanup."""
        self.temp_files.append(path)
        register_temp_file(path)

    def register_handler(self, handler) -> None:
        """Register a handler (e.g., logging handler) for cleanup."""
        self.handlers.append(handler)

    def cleanup(self) -> None:
        """Clean up all registered resources."""
        # Close database connections
        for conn in self.connections:
            try:
                if hasattr(conn, "close"):
                    conn.close()
                    logger.debug("Closed database connection")
            except Exception as e:
                logger.warning(f"Failed to close connection: {e}")

        # Clean up temporary files
        for temp_file in self.temp_files:
            try:
                if temp_file.exists():
                    temp_file.unlink()
                    logger.debug(f"Cleaned up temporary file: {temp_file}")
            except Exception as e:
                logger.warning(f"Failed to clean up {temp_file}: {e}")

        # Close handlers
        for handler in self.handlers:
            try:
                if hasattr(handler, "close"):
                    handler.close()
                    logger.debug("Closed handler")
            except Exception as e:
                logger.warning(f"Failed to close handler: {e}")

        # Clear registries
        self.connections.clear()
        self.temp_files.clear()
        self.handlers.clear()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
        return False


# Global resource manager instance
_global_resource_manager = ResourceManager()


def get_resource_manager() -> ResourceManager:
    """Get the global resource manager instance."""
    return _global_resource_manager


# Register global cleanup
atexit.register(_global_resource_manager.cleanup)

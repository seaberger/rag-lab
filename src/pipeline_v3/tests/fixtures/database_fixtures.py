"""
Shared database fixtures for tests that support both direct instantiation
and DatabaseFactory-based creation for multi-backend testing.
"""

import pytest

try:
    from core.database_factory import DatabaseFactory
except ImportError:
    DatabaseFactory = None


def create_test_registry(config):
    """Create a test DocumentRegistry using DatabaseFactory if available."""
    from core.registry import DocumentRegistry

    if DatabaseFactory and config.database.backend in ["sqlite", "postgresql"]:
        try:
            factory = DatabaseFactory(config)
            if factory.validate_backend_configuration():
                adapters = factory.create_all()
                registry = adapters["registry"]
                # Store factory and adapters for cleanup
                registry._test_factory = factory
                registry._test_adapters = adapters
                return registry
        except Exception:
            pass  # Fall back to direct initialization

    # Direct initialization as fallback
    return DocumentRegistry(config=config)


def create_test_fingerprint_manager(config):
    """Create a test FingerprintManager using DatabaseFactory if available."""
    from core.fingerprint import FingerprintManager

    if DatabaseFactory and config.database.backend in ["sqlite", "postgresql"]:
        try:
            factory = DatabaseFactory(config)
            if factory.validate_backend_configuration():
                adapters = factory.create_all()
                fingerprint_manager = adapters["fingerprint_manager"]
                # Store factory and adapters for cleanup
                fingerprint_manager._test_factory = factory
                fingerprint_manager._test_adapters = adapters
                return fingerprint_manager
        except Exception:
            pass  # Fall back to direct initialization

    # Direct initialization as fallback
    return FingerprintManager(config=config)


def create_test_job_manager(config):
    """Create a test JobManager using DatabaseFactory if available."""
    from job_queue.job import JobManager

    if DatabaseFactory and config.database.backend in ["sqlite", "postgresql"]:
        try:
            factory = DatabaseFactory(config)
            if factory.validate_backend_configuration():
                adapters = factory.create_all()
                job_manager = adapters["job_manager"]
                # Store factory and adapters for cleanup
                job_manager._test_factory = factory
                job_manager._test_adapters = adapters
                return job_manager
        except Exception:
            pass  # Fall back to direct initialization

    # Direct initialization as fallback
    return JobManager(config=config)


def create_test_keyword_index(config):
    """Create a test keyword index using DatabaseFactory if available."""
    from core.keyword_index import KeywordIndex

    if DatabaseFactory and config.database.backend in ["sqlite", "postgresql"]:
        try:
            factory = DatabaseFactory(config)
            if factory.validate_backend_configuration():
                adapters = factory.create_all()
                keyword_index = adapters["keyword_index"]
                # Store factory and adapters for cleanup
                keyword_index._test_factory = factory
                keyword_index._test_adapters = adapters
                return keyword_index
        except Exception:
            pass  # Fall back to direct initialization

    # Direct initialization as fallback
    return KeywordIndex(config=config)


def cleanup_test_component(component):
    """Clean up test component, including DatabaseFactory resources if used."""
    import contextlib

    if hasattr(component, "_test_factory") and hasattr(component, "_test_adapters"):
        with contextlib.suppress(Exception):
            component._test_factory.close_all(component._test_adapters)
    elif hasattr(component, "close"):
        with contextlib.suppress(Exception):
            component.close()


# Fixtures for each component type
@pytest.fixture
def test_registry(test_config):
    """Provide a test DocumentRegistry with automatic cleanup."""
    registry = create_test_registry(test_config)
    yield registry
    cleanup_test_component(registry)


@pytest.fixture
def test_fingerprint_manager(test_config):
    """Provide a test FingerprintManager with automatic cleanup."""
    fingerprint_manager = create_test_fingerprint_manager(test_config)
    yield fingerprint_manager
    cleanup_test_component(fingerprint_manager)


@pytest.fixture
def test_job_manager(test_config):
    """Provide a test JobManager with automatic cleanup."""
    job_manager = create_test_job_manager(test_config)
    yield job_manager
    cleanup_test_component(job_manager)


@pytest.fixture
def test_keyword_index(test_config):
    """Provide a test keyword index with automatic cleanup."""
    keyword_index = create_test_keyword_index(test_config)
    yield keyword_index
    cleanup_test_component(keyword_index)


@pytest.fixture
def test_database_components(test_config):
    """Provide all database components using DatabaseFactory if available."""
    if DatabaseFactory and test_config.database.backend in ["sqlite", "postgresql"]:
        try:
            factory = DatabaseFactory(test_config)
            if factory.validate_backend_configuration():
                adapters = factory.create_all()
                yield adapters
                factory.close_all(adapters)
                return
        except Exception:
            pass  # Fall back to individual components

    # Fallback: create components individually
    from core.fingerprint import FingerprintManager
    from core.keyword_index import KeywordIndex
    from core.registry import DocumentRegistry
    from job_queue.job import JobManager

    components = {
        "registry": DocumentRegistry(config=test_config),
        "fingerprint_manager": FingerprintManager(config=test_config),
        "job_manager": JobManager(config=test_config),
        "keyword_index": KeywordIndex(config=test_config),
    }

    yield components

    # Cleanup
    import contextlib

    for component in components.values():
        if hasattr(component, "close"):
            with contextlib.suppress(Exception):
                component.close()

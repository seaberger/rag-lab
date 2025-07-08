"""
Test Phase 4.2: Connection pooling and performance optimization.

This module tests the Phase 4.2 components including per-tenant connection pooling,
monitoring, and performance optimization without requiring a PostgreSQL connection.
"""

import pytest
import time
from unittest.mock import Mock, patch

from utils.config import PipelineConfig
from core.database_factory import DatabaseFactory
from core.tenant_connection_manager import (
    PoolMetrics,
    TenantPoolConfig,
    TenantConnectionManager
)
from core.tenant_pool_monitor import (
    PoolAlert,
    MonitoringMetrics,
    TenantMetrics,
    TenantPoolMonitor
)
from core.postgres_performance import (
    QueryPerformanceMetric,
    IndexRecommendation,
    PerformanceReport,
    PostgreSQLPerformanceOptimizer
)


class TestPhase42DataStructures:
    """Test Phase 4.2 data structures and basic functionality."""

    def test_pool_metrics_creation(self):
        """Test PoolMetrics data class creation."""
        metrics = PoolMetrics(
            tenant_id="test-tenant",
            pool_name="registry",
            created_at=time.time(),
            total_connections=10,
            active_connections=3,
            idle_connections=7,
            total_queries=100,
            failed_queries=2,
            avg_query_time=50.5,
            last_activity=time.time(),
            pool_health="healthy"
        )

        assert metrics.tenant_id == "test-tenant"
        assert metrics.pool_name == "registry"
        assert metrics.total_connections == 10
        assert metrics.active_connections == 3
        assert metrics.pool_health == "healthy"

    def test_tenant_pool_config_creation(self):
        """Test TenantPoolConfig data class creation."""
        config = TenantPoolConfig(
            tenant_id="test-tenant",
            min_connections=2,
            max_connections=10,
            connection_timeout=30,
            idle_timeout=300
        )

        assert config.tenant_id == "test-tenant"
        assert config.min_connections == 2
        assert config.max_connections == 10
        assert config.connection_timeout == 30

    def test_pool_alert_creation(self):
        """Test PoolAlert data class creation."""
        alert = PoolAlert(
            tenant_id="test-tenant",
            schema="registry",
            alert_type="degraded",
            message="Pool performance degraded",
            timestamp=time.time()
        )

        assert alert.tenant_id == "test-tenant"
        assert alert.schema == "registry"
        assert alert.alert_type == "degraded"
        assert alert.resolved is False
        assert alert.resolution_time is None

    def test_monitoring_metrics_creation(self):
        """Test MonitoringMetrics data class creation."""
        metrics = MonitoringMetrics(
            timestamp=time.time(),
            total_pools=3,
            healthy_pools=2,
            degraded_pools=1,
            critical_pools=0,
            total_connections=30,
            active_connections=12,
            average_pool_age=3600.0,
            connection_utilization=40.0,
            alerts_active=1,
            alerts_resolved_last_hour=0
        )

        assert metrics.total_pools == 3
        assert metrics.healthy_pools == 2
        assert metrics.connection_utilization == 40.0
        assert metrics.alerts_active == 1

    def test_tenant_metrics_creation(self):
        """Test TenantMetrics data class creation."""
        metrics = TenantMetrics(
            tenant_id="test-tenant",
            pool_count=2,
            total_connections=20,
            active_connections=5,
            healthy_pools=2,
            degraded_pools=0,
            critical_pools=0,
            utilization_percent=25.0,
            oldest_pool_age=7200.0,
            newest_pool_age=3600.0
        )

        assert metrics.tenant_id == "test-tenant"
        assert metrics.pool_count == 2
        assert metrics.utilization_percent == 25.0
        assert metrics.oldest_pool_age == 7200.0


class TestPhase42PerformanceStructures:
    """Test Phase 4.2 performance optimization data structures."""

    def test_query_performance_metric_creation(self):
        """Test QueryPerformanceMetric data class creation."""
        metric = QueryPerformanceMetric(
            query_signature="SELECT * FROM documents WHERE tenant_id = ?",
            execution_count=1000,
            total_time_ms=5000.0,
            average_time_ms=5.0,
            min_time_ms=1.0,
            max_time_ms=50.0,
            rows_examined=10000,
            rows_returned=100,
            cache_hit_ratio=0.95,
            optimization_suggestions=["Avoid SELECT * - specify only needed columns"]
        )

        assert metric.query_signature == "SELECT * FROM documents WHERE tenant_id = ?"
        assert metric.execution_count == 1000
        assert metric.average_time_ms == 5.0
        assert len(metric.optimization_suggestions) == 1

    def test_index_recommendation_creation(self):
        """Test IndexRecommendation data class creation."""
        recommendation = IndexRecommendation(
            table_name="documents",
            schema_name="public",
            index_type="btree",
            columns=["tenant_id", "state"],
            estimated_benefit="high",
            reason="Queries filtering by tenant and state",
            estimated_size_mb=5.0,
            create_statement="CREATE INDEX idx_documents_tenant_state ON documents (tenant_id, state);"
        )

        assert recommendation.table_name == "documents"
        assert recommendation.index_type == "btree"
        assert recommendation.estimated_benefit == "high"
        assert len(recommendation.columns) == 2
        assert "CREATE INDEX" in recommendation.create_statement

    def test_performance_report_creation(self):
        """Test PerformanceReport data class creation."""
        query_metric = QueryPerformanceMetric(
            query_signature="SELECT * FROM test",
            execution_count=100,
            total_time_ms=1000.0,
            average_time_ms=10.0,
            min_time_ms=5.0,
            max_time_ms=20.0,
            rows_examined=1000,
            rows_returned=50,
            cache_hit_ratio=0.95,
            optimization_suggestions=["Test suggestion"]
        )

        index_rec = IndexRecommendation(
            table_name="test_table",
            schema_name="public",
            index_type="btree",
            columns=["id"],
            estimated_benefit="medium",
            reason="Test reason",
            estimated_size_mb=2.0,
            create_statement="CREATE INDEX test_idx ON test_table (id);"
        )

        report = PerformanceReport(
            timestamp=time.time(),
            database_size_mb=1024.0,
            connection_count=20,
            active_connections=5,
            cache_hit_ratio=0.98,
            slow_queries=[query_metric],
            index_recommendations=[index_rec],
            configuration_suggestions=["Increase shared_buffers"],
            maintenance_recommendations=["Run VACUUM"]
        )

        assert report.database_size_mb == 1024.0
        assert report.connection_count == 20
        assert len(report.slow_queries) == 1
        assert len(report.index_recommendations) == 1
        assert len(report.configuration_suggestions) == 1


class TestPhase42DatabaseFactoryIntegration:
    """Test Phase 4.2 database factory integration."""

    def test_database_factory_sqlite_backend(self):
        """Test database factory with SQLite backend (no connection manager)."""
        config = PipelineConfig()
        # Explicitly set SQLite backend (PostgreSQL is now default)
        config.database.backend = "sqlite"
        factory = DatabaseFactory(config, tenant_id="test-tenant")

        # Should be SQLite backend when explicitly configured
        assert factory.backend == "sqlite"
        assert factory.tenant_id == "test-tenant"
        assert factory._connection_manager is None

        # Test validation
        assert factory.validate_backend_configuration() is True

        # Test migration info
        migration_info = factory.get_migration_info()
        assert migration_info["current_backend"] == "sqlite"
        assert migration_info["migration_available"] is True

    @patch('core.tenant_connection_manager.get_tenant_connection_manager')
    def test_database_factory_postgresql_backend(self, mock_get_manager):
        """Test database factory with PostgreSQL backend (with connection manager)."""
        # Mock connection manager
        mock_manager = Mock()
        mock_get_manager.return_value = mock_manager

        # Create config with PostgreSQL backend
        config = PipelineConfig()
        # Manually set backend to postgresql for test
        config.database.backend = "postgresql"

        factory = DatabaseFactory(config, tenant_id="test-tenant")

        assert factory.backend == "postgresql"
        assert factory.tenant_id == "test-tenant"
        assert factory._connection_manager == mock_manager

        # Verify connection manager was requested
        mock_get_manager.assert_called_once_with(config)

    def test_database_factory_create_registry_sqlite(self):
        """Test creating document registry with SQLite backend."""
        config = PipelineConfig()
        factory = DatabaseFactory(config)

        registry = factory.create_document_registry()

        # Should create SQLite registry
        assert registry is not None
        assert "DocumentRegistry" in str(type(registry))

        # Clean up
        registry.close()


class TestPhase42MockFunctionality:
    """Test Phase 4.2 functionality with mocked dependencies."""

    @patch('core.postgres_performance.PostgreSQLBase')
    def test_performance_optimizer_initialization(self, mock_pg_base):
        """Test PostgreSQL performance optimizer initialization."""
        config = PipelineConfig()
        config.database.backend = "postgresql"
        config.database.postgresql = Mock()

        optimizer = PostgreSQLPerformanceOptimizer(config)

        assert optimizer.config == config
        assert optimizer.slow_query_threshold_ms == 1000
        assert optimizer.low_cache_hit_ratio == 0.95

    def test_performance_optimizer_query_suggestions(self):
        """Test query optimization suggestions."""
        config = PipelineConfig()
        config.database.backend = "postgresql"
        config.database.postgresql = Mock()

        optimizer = PostgreSQLPerformanceOptimizer(config)

        # Test query with common anti-patterns
        query = "SELECT * FROM documents WHERE name LIKE '%test%' OR status = 'active'"
        suggestions = optimizer._generate_query_suggestions(query)

        assert len(suggestions) > 0
        assert any("SELECT *" in suggestion for suggestion in suggestions)
        assert any("LIKE patterns" in suggestion for suggestion in suggestions)

    @patch('core.tenant_pool_monitor.TenantConnectionManager')
    def test_pool_monitor_initialization(self, mock_manager):
        """Test pool monitor initialization."""
        config = PipelineConfig()
        mock_connection_manager = Mock()

        monitor = TenantPoolMonitor(mock_connection_manager, config)

        assert monitor.connection_manager == mock_connection_manager
        assert monitor.config == config
        assert monitor.monitoring_interval == 30
        assert monitor.degraded_threshold == 0.8

    def test_pool_monitor_metrics_collection(self):
        """Test pool monitor metrics collection with mock data."""
        config = PipelineConfig()
        mock_connection_manager = Mock()

        # Mock pool metrics
        mock_metrics = [
            PoolMetrics(
                tenant_id="tenant1",
                pool_name="registry",
                created_at=time.time() - 3600,
                total_connections=10,
                active_connections=3,
                idle_connections=7,
                total_queries=100,
                failed_queries=0,
                avg_query_time=25.0,
                last_activity=time.time() - 60,
                pool_health="healthy"
            ),
            PoolMetrics(
                tenant_id="tenant2",
                pool_name="search",
                created_at=time.time() - 1800,
                total_connections=8,
                active_connections=6,
                idle_connections=2,
                total_queries=200,
                failed_queries=5,
                avg_query_time=75.0,
                last_activity=time.time() - 30,
                pool_health="degraded"
            )
        ]

        mock_connection_manager.get_pool_metrics.return_value = mock_metrics

        monitor = TenantPoolMonitor(mock_connection_manager, config)
        metrics = monitor.collect_metrics()

        assert metrics.total_pools == 2
        assert metrics.healthy_pools == 1
        assert metrics.degraded_pools == 1
        assert metrics.total_connections == 18
        assert metrics.active_connections == 9


@pytest.mark.integration
class TestPhase42Integration:
    """Integration tests for Phase 4.2 components."""

    def test_complete_phase42_integration_sqlite(self):
        """Test complete Phase 4.2 integration with SQLite backend."""
        # This test verifies that all Phase 4.2 components work together
        # without requiring PostgreSQL

        config = PipelineConfig()

        # Test database factory
        factory = DatabaseFactory(config, tenant_id="integration-test")
        assert factory.backend == "sqlite"
        assert factory._connection_manager is None

        # Test registry creation
        registry = factory.create_document_registry()
        assert registry is not None

        # Test CLI command functions exist
        from cli.commands import (
            add_pool_monitor_subcommands,
            add_performance_subcommands
        )

        # These should be callable functions
        assert callable(add_pool_monitor_subcommands)
        assert callable(add_performance_subcommands)

        # Clean up
        registry.close()

    def test_all_phase42_imports_work(self):
        """Test that all Phase 4.2 imports work correctly."""
        # Connection manager components
        from core.tenant_connection_manager import (
            TenantConnectionManager,
            get_tenant_connection_manager,
            PoolMetrics,
            TenantPoolConfig
        )

        # Monitoring components
        from core.tenant_pool_monitor import (
            TenantPoolMonitor,
            get_pool_monitor,
            PoolAlert,
            MonitoringMetrics,
            TenantMetrics
        )

        # Performance optimization components
        from core.postgres_performance import (
            PostgreSQLPerformanceOptimizer,
            get_performance_optimizer,
            QueryPerformanceMetric,
            IndexRecommendation,
            PerformanceReport
        )

        # CLI components
        from cli.commands.pool_monitor import add_pool_monitor_subcommands
        from cli.commands.performance import add_performance_subcommands

        # Updated database factory
        from core.database_factory import DatabaseFactory

        # All imports should succeed
        assert True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

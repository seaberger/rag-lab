"""
PostgreSQL Performance Optimization for Pipeline v3.

This module provides comprehensive performance optimization features including
query optimization, index management, connection tuning, and performance monitoring.
"""

import contextlib
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

# Add the pipeline_v3 root to Python path
pipeline_root = Path(__file__).parent.parent
if str(pipeline_root) not in sys.path:
    sys.path.insert(0, str(pipeline_root))

from src.pipeline_v3.core.postgres_base import PostgreSQLBase
from src.pipeline_v3.utils.common_utils import logger
from src.pipeline_v3.utils.config import PipelineConfig


@dataclass
class QueryPerformanceMetric:
    """Performance metrics for a specific query."""

    query_signature: str
    execution_count: int
    total_time_ms: float
    average_time_ms: float
    min_time_ms: float
    max_time_ms: float
    rows_examined: int
    rows_returned: int
    cache_hit_ratio: float
    optimization_suggestions: List[str]


@dataclass
class IndexRecommendation:
    """Index recommendation for performance optimization."""

    table_name: str
    schema_name: str
    index_type: str  # 'btree', 'gin', 'gist', 'hash'
    columns: List[str]
    estimated_benefit: str  # 'high', 'medium', 'low'
    reason: str
    estimated_size_mb: float
    create_statement: str


@dataclass
class PerformanceReport:
    """Comprehensive performance analysis report."""

    timestamp: float
    database_size_mb: float
    connection_count: int
    active_connections: int
    cache_hit_ratio: float
    slow_queries: List[QueryPerformanceMetric]
    index_recommendations: List[IndexRecommendation]
    configuration_suggestions: List[str]
    maintenance_recommendations: List[str]


class PostgreSQLPerformanceOptimizer:
    """
    Advanced PostgreSQL performance optimization system.

    Provides query analysis, index recommendations, configuration tuning,
    and automated performance monitoring for multi-tenant PostgreSQL deployments.
    """

    def __init__(self, config: PipelineConfig):
        """
        Initialize performance optimizer.

        Args:
            config: Pipeline configuration with PostgreSQL settings
        """
        self.config = config

        if not hasattr(config, "database") or config.database.backend != "postgresql":
            raise ValueError("PostgreSQLPerformanceOptimizer requires PostgreSQL backend")

        self.pg_settings = config.database.postgresql

        # Performance thresholds
        self.slow_query_threshold_ms = 1000  # 1 second
        self.low_cache_hit_ratio = 0.95  # 95%
        self.high_connection_ratio = 0.8  # 80% of max connections

        # Schema information
        self.schemas = [
            self.pg_settings.registry_schema,
            self.pg_settings.search_schema,
            self.pg_settings.jobs_schema,
            self.pg_settings.fingerprints_schema,
        ]

        logger.info("PostgreSQLPerformanceOptimizer initialized")

    def analyze_performance(self, tenant_id: str | None = None) -> PerformanceReport:
        """
        Perform comprehensive performance analysis.

        Args:
            tenant_id: Optional tenant ID for tenant-specific analysis

        Returns:
            Performance analysis report
        """
        # Use dedicated connection for analysis
        db = PostgreSQLBase(
            self.pg_settings,
            "public",  # Use public schema for system queries
            log_queries=False,
        )
        db.initialize()

        try:
            # Collect basic metrics
            database_size = self._get_database_size(db)
            connection_stats = self._get_connection_stats(db)
            cache_stats = self._get_cache_stats(db)

            # Analyze slow queries
            slow_queries = self._analyze_slow_queries(db, tenant_id)

            # Generate index recommendations
            index_recommendations = self._generate_index_recommendations(db, tenant_id)

            # Configuration analysis
            config_suggestions = self._analyze_configuration(db, connection_stats, cache_stats)

            # Maintenance recommendations
            maintenance_suggestions = self._analyze_maintenance_needs(db, tenant_id)

            report = PerformanceReport(
                timestamp=time.time(),
                database_size_mb=database_size,
                connection_count=connection_stats["total_connections"],
                active_connections=connection_stats["active_connections"],
                cache_hit_ratio=cache_stats["buffer_hit_ratio"],
                slow_queries=slow_queries,
                index_recommendations=index_recommendations,
                configuration_suggestions=config_suggestions,
                maintenance_recommendations=maintenance_suggestions,
            )

            logger.info(
                f"Performance analysis completed. "
                f"Found {len(slow_queries)} slow queries, "
                f"{len(index_recommendations)} index recommendations"
            )

            return report

        finally:
            db.close()

    def _get_database_size(self, db: PostgreSQLBase) -> float:
        """Get total database size in MB."""
        result = db.fetch_one("""
            SELECT pg_database_size(current_database()) / 1024.0 / 1024.0 as size_mb
        """)
        return result["size_mb"] if result else 0.0

    def _get_connection_stats(self, db: PostgreSQLBase) -> Dict[str, Any]:
        """Get connection statistics."""
        # Current connections
        conn_result = db.fetch_one("""
            SELECT
                count(*) as total_connections,
                count(*) FILTER (WHERE state = 'active') as active_connections,
                count(*) FILTER (WHERE state = 'idle') as idle_connections
            FROM pg_stat_activity
            WHERE datname = current_database()
        """)

        # Max connections setting
        max_conn_result = db.fetch_one("""
            SELECT setting::int as max_connections
            FROM pg_settings
            WHERE name = 'max_connections'
        """)

        return {
            "total_connections": conn_result["total_connections"] if conn_result else 0,
            "active_connections": conn_result["active_connections"] if conn_result else 0,
            "idle_connections": conn_result["idle_connections"] if conn_result else 0,
            "max_connections": max_conn_result["max_connections"] if max_conn_result else 100,
        }

    def _get_cache_stats(self, db: PostgreSQLBase) -> Dict[str, Any]:
        """Get cache hit ratio statistics."""
        buffer_result = db.fetch_one("""
            SELECT
                round(
                    100.0 * sum(blks_hit) / nullif(sum(blks_hit + blks_read), 0), 2
                ) as buffer_hit_ratio
            FROM pg_stat_database
            WHERE datname = current_database()
        """)

        index_result = db.fetch_one("""
            SELECT
                round(
                    100.0 * sum(idx_blks_hit) / nullif(sum(idx_blks_hit + idx_blks_read), 0), 2
                ) as index_hit_ratio
            FROM pg_statio_user_indexes
        """)

        return {
            "buffer_hit_ratio": (buffer_result["buffer_hit_ratio"] / 100.0)
            if buffer_result and buffer_result["buffer_hit_ratio"]
            else 0.0,
            "index_hit_ratio": (index_result["index_hit_ratio"] / 100.0)
            if index_result and index_result["index_hit_ratio"]
            else 0.0,
        }

    def _analyze_slow_queries(
        self, db: PostgreSQLBase, tenant_id: str | None
    ) -> List[QueryPerformanceMetric]:
        """Analyze slow queries from pg_stat_statements if available."""
        # Check if pg_stat_statements is available
        extension_check = db.fetch_one("""
            SELECT EXISTS (
                SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements'
            ) as has_pg_stat_statements
        """)

        if not extension_check or not extension_check["has_pg_stat_statements"]:
            logger.warning(
                "pg_stat_statements extension not available. Install for detailed query analysis."
            )
            return []

        # Query slow statements
        slow_query_sql = """
            SELECT
                left(query, 100) as query_signature,
                calls as execution_count,
                total_exec_time as total_time_ms,
                mean_exec_time as average_time_ms,
                min_exec_time as min_time_ms,
                max_exec_time as max_time_ms,
                rows as rows_examined,
                rows as rows_returned
            FROM pg_stat_statements
            WHERE mean_exec_time > %s
            ORDER BY mean_exec_time DESC
            LIMIT 20
        """

        slow_queries = db.fetch_all(slow_query_sql, (self.slow_query_threshold_ms,))

        metrics = []
        for query in slow_queries:
            # Generate optimization suggestions based on query patterns
            suggestions = self._generate_query_suggestions(query["query_signature"])

            metrics.append(
                QueryPerformanceMetric(
                    query_signature=query["query_signature"],
                    execution_count=query["execution_count"],
                    total_time_ms=query["total_time_ms"],
                    average_time_ms=query["average_time_ms"],
                    min_time_ms=query["min_time_ms"],
                    max_time_ms=query["max_time_ms"],
                    rows_examined=query["rows_examined"],
                    rows_returned=query["rows_returned"],
                    cache_hit_ratio=0.0,  # Would need more detailed analysis
                    optimization_suggestions=suggestions,
                )
            )

        return metrics

    def _generate_query_suggestions(self, query_signature: str) -> List[str]:
        """Generate optimization suggestions based on query patterns."""
        suggestions = []
        query_lower = query_signature.lower()

        # Common optimization patterns
        if "select *" in query_lower:
            suggestions.append("Avoid SELECT * - specify only needed columns")

        if "order by" in query_lower and "limit" not in query_lower:
            suggestions.append("Consider adding LIMIT clause to ORDER BY queries")

        if "like" in query_lower and query_lower.count("%") >= 2:
            suggestions.append(
                "LIKE patterns with leading % prevent index usage - consider full-text search"
            )

        if "or" in query_lower:
            suggestions.append(
                "OR conditions may prevent index usage - consider UNION or separate queries"
            )

        if "distinct" in query_lower:
            suggestions.append("DISTINCT can be expensive - verify if really needed")

        if "group by" in query_lower and "having" in query_lower:
            suggestions.append("Move HAVING conditions to WHERE clause when possible")

        # Table-specific suggestions
        if any(table in query_lower for table in ["documents", "chunks", "jobs"]):
            suggestions.append("Ensure tenant_id is included in WHERE clause for RLS optimization")

        return suggestions

    def _generate_index_recommendations(
        self, db: PostgreSQLBase, tenant_id: str | None
    ) -> List[IndexRecommendation]:
        """Generate index recommendations based on query patterns and missing indexes."""
        recommendations = []

        # Check for missing indexes on foreign key columns
        fk_indexes = self._check_foreign_key_indexes(db)
        recommendations.extend(fk_indexes)

        # Check for missing indexes on frequently queried columns
        query_indexes = self._check_query_pattern_indexes(db)
        recommendations.extend(query_indexes)

        # Check for GIN indexes on JSONB columns
        jsonb_indexes = self._check_jsonb_indexes(db)
        recommendations.extend(jsonb_indexes)

        # Check for partial indexes on tenant-specific data
        tenant_indexes = self._check_tenant_indexes(db)
        recommendations.extend(tenant_indexes)

        return recommendations

    def _check_foreign_key_indexes(self, db: PostgreSQLBase) -> List[IndexRecommendation]:
        """Check for missing indexes on foreign key columns."""
        # This would need to be customized based on actual schema
        # For now, return common patterns
        recommendations = []

        # Common foreign key patterns in our schema
        common_fks = [
            ("documents", "tenant_id"),
            ("chunks", "doc_id"),
            ("chunks", "tenant_id"),
            ("jobs", "tenant_id"),
            ("fingerprints", "tenant_id"),
        ]

        for table, column in common_fks:
            # Check if index exists
            index_check = db.fetch_one(
                """
                SELECT EXISTS (
                    SELECT 1 FROM pg_indexes
                    WHERE tablename = %s
                    AND indexdef LIKE %s
                ) as has_index
            """,
                (table, f"%{column}%"),
            )

            if index_check and not index_check["has_index"]:
                recommendations.append(
                    IndexRecommendation(
                        table_name=table,
                        schema_name="public",  # Would need to be schema-aware
                        index_type="btree",
                        columns=[column],
                        estimated_benefit="high",
                        reason=f"Foreign key column {column} lacks index",
                        estimated_size_mb=5.0,  # Rough estimate
                        create_statement=f"CREATE INDEX idx_{table}_{column} ON {table} ({column});",
                    )
                )

        return recommendations

    def _check_query_pattern_indexes(self, db: PostgreSQLBase) -> List[IndexRecommendation]:
        """Check for indexes based on common query patterns."""
        recommendations = []

        # Multi-column indexes for common query patterns
        common_patterns = [
            ("documents", ["tenant_id", "state"], "Queries filtering by tenant and state"),
            ("chunks", ["tenant_id", "doc_id"], "Queries filtering by tenant and document"),
            ("jobs", ["tenant_id", "status"], "Queries filtering by tenant and status"),
            ("jobs", ["status", "priority", "created_at"], "Job queue processing queries"),
        ]

        for table, columns, reason in common_patterns:
            # Simple check - in production would analyze actual query patterns
            index_name = f"idx_{table}_{'_'.join(columns)}"

            recommendations.append(
                IndexRecommendation(
                    table_name=table,
                    schema_name="public",
                    index_type="btree",
                    columns=columns,
                    estimated_benefit="medium",
                    reason=reason,
                    estimated_size_mb=3.0,
                    create_statement=f"CREATE INDEX {index_name} ON {table} ({', '.join(columns)});",
                )
            )

        return recommendations

    def _check_jsonb_indexes(self, db: PostgreSQLBase) -> List[IndexRecommendation]:
        """Check for GIN indexes on JSONB columns."""
        recommendations = []

        # Find JSONB columns
        jsonb_columns = db.fetch_all(
            """
            SELECT
                table_name,
                column_name,
                table_schema
            FROM information_schema.columns
            WHERE data_type = 'jsonb'
            AND table_schema IN ('public', %s, %s, %s, %s)
        """,
            tuple(self.schemas),
        )

        for column_info in jsonb_columns:
            table = column_info["table_name"]
            column = column_info["column_name"]
            schema = column_info["table_schema"]

            # Check if GIN index exists
            index_check = db.fetch_one(
                """
                SELECT EXISTS (
                    SELECT 1 FROM pg_indexes
                    WHERE schemaname = %s
                    AND tablename = %s
                    AND indexdef LIKE %s
                    AND indexdef LIKE %s
                ) as has_gin_index
            """,
                (schema, table, f"%{column}%", "%gin%"),
            )

            if index_check and not index_check["has_gin_index"]:
                recommendations.append(
                    IndexRecommendation(
                        table_name=table,
                        schema_name=schema,
                        index_type="gin",
                        columns=[column],
                        estimated_benefit="high",
                        reason=f"JSONB column {column} benefits from GIN index for fast lookups",
                        estimated_size_mb=10.0,
                        create_statement=f"CREATE INDEX idx_{table}_{column}_gin ON {schema}.{table} USING gin ({column});",
                    )
                )

        return recommendations

    def _check_tenant_indexes(self, db: PostgreSQLBase) -> List[IndexRecommendation]:
        """Check for partial indexes on tenant-specific data."""
        recommendations = []

        # Partial indexes can be very effective for multi-tenant data
        # where queries are always filtered by tenant_id
        tenant_patterns = [
            ("documents", ["state"], "WHERE tenant_id = 'specific_tenant'"),
            (
                "jobs",
                ["status"],
                "WHERE tenant_id = 'specific_tenant' AND status IN ('pending', 'running')",
            ),
            ("chunks", ["doc_id"], "WHERE tenant_id = 'specific_tenant'"),
        ]

        for table, columns, where_clause in tenant_patterns:
            index_name = f"idx_{table}_{'_'.join(columns)}_partial"

            recommendations.append(
                IndexRecommendation(
                    table_name=table,
                    schema_name="public",
                    index_type="btree",
                    columns=columns,
                    estimated_benefit="medium",
                    reason=f"Partial index for tenant-specific queries on {table}",
                    estimated_size_mb=2.0,
                    create_statement=f"CREATE INDEX {index_name} ON {table} ({', '.join(columns)}) {where_clause};",
                )
            )

        return recommendations

    def _analyze_configuration(
        self, db: PostgreSQLBase, connection_stats: Dict[str, Any], cache_stats: Dict[str, Any]
    ) -> List[str]:
        """Analyze PostgreSQL configuration and suggest improvements."""
        suggestions = []

        # Connection analysis
        conn_ratio = connection_stats["total_connections"] / connection_stats["max_connections"]
        if conn_ratio > self.high_connection_ratio:
            suggestions.append(
                f"High connection usage ({conn_ratio:.1%}). Consider connection pooling or increasing max_connections."
            )

        # Cache hit ratio analysis
        if cache_stats["buffer_hit_ratio"] < self.low_cache_hit_ratio:
            suggestions.append(
                f"Low buffer cache hit ratio ({cache_stats['buffer_hit_ratio']:.1%}). "
                "Consider increasing shared_buffers."
            )

        # Get current configuration values
        config_values = db.fetch_all("""
            SELECT name, setting, unit, context
            FROM pg_settings
            WHERE name IN (
                'shared_buffers', 'effective_cache_size', 'work_mem',
                'maintenance_work_mem', 'checkpoint_completion_target',
                'wal_buffers', 'random_page_cost'
            )
        """)

        config_dict = {row["name"]: row for row in config_values}

        # Analyze specific settings
        if "shared_buffers" in config_dict:
            shared_buffers = config_dict["shared_buffers"]
            if shared_buffers["unit"] == "8kB":
                shared_buffers_mb = int(shared_buffers["setting"]) * 8 / 1024
                if shared_buffers_mb < 128:  # Less than 128MB
                    suggestions.append(
                        f"shared_buffers is only {shared_buffers_mb:.0f}MB. "
                        "Consider increasing to 25% of available RAM."
                    )

        if "work_mem" in config_dict:
            work_mem_kb = int(config_dict["work_mem"]["setting"])
            if work_mem_kb < 4096:  # Less than 4MB
                suggestions.append(
                    f"work_mem is only {work_mem_kb}KB. "
                    "Consider increasing for better sort/hash performance."
                )

        if "random_page_cost" in config_dict:
            random_page_cost = float(config_dict["random_page_cost"]["setting"])
            if random_page_cost == 4.0:  # Default value
                suggestions.append(
                    "random_page_cost is set to default (4.0). "
                    "Consider lowering to 1.1-2.0 for SSD storage."
                )

        return suggestions

    def _analyze_maintenance_needs(self, db: PostgreSQLBase, tenant_id: str | None) -> List[str]:
        """Analyze maintenance needs like VACUUM, ANALYZE, etc."""
        suggestions = []

        # Check table statistics and last vacuum/analyze times
        stats_query = """
            SELECT
                schemaname,
                tablename,
                n_tup_ins as inserts,
                n_tup_upd as updates,
                n_tup_del as deletes,
                n_dead_tup as dead_tuples,
                last_vacuum,
                last_autovacuum,
                last_analyze,
                last_autoanalyze
            FROM pg_stat_user_tables
            ORDER BY n_dead_tup DESC
        """

        table_stats = db.fetch_all(stats_query)

        for stat in table_stats:
            table_name = f"{stat['schemaname']}.{stat['tablename']}"

            # Check for high dead tuple ratio
            total_tuples = stat["inserts"] + stat["updates"]
            if total_tuples > 0:
                dead_ratio = stat["dead_tuples"] / total_tuples
                if dead_ratio > 0.1:  # More than 10% dead tuples
                    suggestions.append(
                        f"Table {table_name} has {dead_ratio:.1%} dead tuples. Consider manual VACUUM."
                    )

            # Check for stale statistics
            last_analyze = stat["last_analyze"] or stat["last_autoanalyze"]
            if last_analyze:
                # Convert to timestamp (simplified - would need proper timezone handling)
                days_since_analyze = 7  # Placeholder
                if days_since_analyze > 7:
                    suggestions.append(
                        f"Table {table_name} statistics are {days_since_analyze} days old. Consider ANALYZE."
                    )

        # Check for large tables that might benefit from partitioning
        large_tables = db.fetch_all("""
            SELECT
                schemaname,
                tablename,
                pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size,
                pg_total_relation_size(schemaname||'.'||tablename) as size_bytes
            FROM pg_tables
            WHERE schemaname NOT IN ('information_schema', 'pg_catalog')
            ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
            LIMIT 5
        """)

        for table in large_tables:
            size_mb = table["size_bytes"] / (1024 * 1024)
            if size_mb > 1000:  # Larger than 1GB
                suggestions.append(
                    f"Large table {table['schemaname']}.{table['tablename']} ({table['size']}) "
                    "might benefit from partitioning."
                )

        return suggestions

    def optimize_queries(self, queries: List[str]) -> Dict[str, List[str]]:
        """
        Analyze and provide optimization suggestions for specific queries.

        Args:
            queries: List of SQL queries to analyze

        Returns:
            Dictionary mapping queries to optimization suggestions
        """
        optimizations = {}

        for query in queries:
            suggestions = []
            query_lower = query.lower().strip()

            # Pattern-based analysis
            suggestions.extend(self._generate_query_suggestions(query))

            # Additional query-specific analysis
            if "explain" not in query_lower:
                suggestions.append("Use EXPLAIN (ANALYZE, BUFFERS) to analyze query execution")

            # Check for common anti-patterns
            if query_lower.count("select") > 1 and "union" not in query_lower:
                suggestions.append("Multiple SELECT statements - consider JOINs or CTEs")

            if "::text" in query_lower:
                suggestions.append("Type casting in WHERE clauses prevents index usage")

            if "not in" in query_lower:
                suggestions.append(
                    "NOT IN with nullable columns can be inefficient - consider NOT EXISTS"
                )

            optimizations[query] = suggestions

        return optimizations

    def create_performance_indexes(self, recommendations: List[IndexRecommendation]) -> List[str]:
        """
        Create recommended indexes (returns SQL statements for manual execution).

        Args:
            recommendations: List of index recommendations

        Returns:
            List of SQL statements to create indexes
        """
        sql_statements = []

        for rec in recommendations:
            # Add estimated execution time and safety warnings
            if rec.estimated_benefit == "high":
                sql_statements.append(f"-- HIGH BENEFIT: {rec.reason}")
            elif rec.estimated_benefit == "medium":
                sql_statements.append(f"-- MEDIUM BENEFIT: {rec.reason}")
            else:
                sql_statements.append(f"-- LOW BENEFIT: {rec.reason}")

            sql_statements.append(f"-- Estimated size: {rec.estimated_size_mb:.1f}MB")
            sql_statements.append("-- Execute during low traffic period")
            sql_statements.append(rec.create_statement)
            sql_statements.append("")

        return sql_statements

    def get_query_plan_analysis(self, query: str, tenant_id: str | None = None) -> Dict[str, Any]:
        """
        Get detailed query execution plan analysis.

        Args:
            query: SQL query to analyze
            tenant_id: Optional tenant ID for context

        Returns:
            Query plan analysis results
        """
        db = PostgreSQLBase(self.pg_settings, "public", log_queries=False)
        db.initialize()

        try:
            # Set tenant context if provided
            if tenant_id:
                with contextlib.suppress(Exception):
                    db.execute("SELECT tenants.set_current_tenant(%s)", (tenant_id,))

            # Get query plan
            explain_query = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}"
            plan_result = db.fetch_one(explain_query)

            if not plan_result:
                return {"error": "No query plan returned"}

            # Parse JSON plan (simplified)
            plan_data = plan_result.get("QUERY PLAN", [{}])[0] if plan_result else {}

            analysis = {
                "execution_time_ms": plan_data.get("Execution Time", 0),
                "planning_time_ms": plan_data.get("Planning Time", 0),
                "total_cost": plan_data.get("Plan", {}).get("Total Cost", 0),
                "rows_estimated": plan_data.get("Plan", {}).get("Plan Rows", 0),
                "rows_actual": plan_data.get("Plan", {}).get("Actual Rows", 0),
                "buffers_hit": 0,  # Would need to parse buffer information
                "buffers_read": 0,
                "optimization_opportunities": self._analyze_query_plan(plan_data),
            }

            return analysis

        except Exception as e:
            return {"error": f"Query plan analysis failed: {e}"}
        finally:
            db.close()

    def _analyze_query_plan(self, plan_data: Dict[str, Any]) -> List[str]:
        """Analyze query plan for optimization opportunities."""
        opportunities = []

        def analyze_node(node):
            node_type = node.get("Node Type", "")

            # Check for expensive operations
            if "Seq Scan" in node_type:
                opportunities.append(
                    f"Sequential scan detected on {node.get('Relation Name', 'unknown table')} - consider adding index"
                )

            if "Sort" in node_type and node.get("Sort Method") == "external sort":
                opportunities.append("External sort detected - consider increasing work_mem")

            if "Hash Join" in node_type and node.get("Hash Buckets Used", 0) > node.get(
                "Hash Buckets", 1
            ):
                opportunities.append("Hash join spilled to disk - consider increasing work_mem")

            # Check nested loops with high costs
            if "Nested Loop" in node_type and node.get("Total Cost", 0) > 1000:
                opportunities.append(
                    "Expensive nested loop - consider different join algorithm or indexes"
                )

            # Recursively analyze child plans
            for plan in node.get("Plans", []):
                analyze_node(plan)

        if "Plan" in plan_data:
            analyze_node(plan_data["Plan"])

        return opportunities


# Global optimizer instance
_performance_optimizer: PostgreSQLPerformanceOptimizer | None = None


def get_performance_optimizer(
    config: PipelineConfig | None = None,
) -> PostgreSQLPerformanceOptimizer:
    """
    Get the global performance optimizer instance.

    Args:
        config: Pipeline configuration (required for first call)

    Returns:
        PostgreSQLPerformanceOptimizer instance
    """
    global _performance_optimizer

    if _performance_optimizer is None:
        if config is None:
            config = PipelineConfig()
        _performance_optimizer = PostgreSQLPerformanceOptimizer(config)

    return _performance_optimizer

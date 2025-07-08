#!/usr/bin/env python3
"""
Set up PostgreSQL database for RAG Lab Pipeline v3.

This script:
1. Creates the database if it doesn't exist
2. Creates all required tables with proper schemas
3. Sets up indexes for performance
4. Configures row-level security for multi-tenancy
"""

import os
import sys
from pathlib import Path

import psycopg
from psycopg import sql

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.pipeline_v3.utils.common_utils import logger
from src.pipeline_v3.utils.config import PipelineConfig


def setup_database(config: PipelineConfig):
    """Set up PostgreSQL database and tables."""

    # Get connection parameters
    pg_config = config.database.postgresql

    # First connect to postgres database to create our database
    logger.info("Connecting to PostgreSQL...")
    try:
        # Connect to default postgres database
        conn = psycopg.connect(
            host=pg_config.host,
            port=pg_config.port,
            dbname="postgres",
            user=pg_config.user,
            password=os.getenv("POSTGRES_PASSWORD", pg_config.password),
        )
        conn.autocommit = True
        cur = conn.cursor()

        # Check if database exists
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (pg_config.database,))
        if not cur.fetchone():
            logger.info(f"Creating database {pg_config.database}...")
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(pg_config.database)))
        else:
            logger.info(f"Database {pg_config.database} already exists")

        cur.close()
        conn.close()

    except Exception as e:
        logger.error(f"Failed to create database: {e}")
        sys.exit(1)

    # Now connect to our database to create tables
    logger.info(f"Connecting to {pg_config.database} database...")
    try:
        conn = psycopg.connect(
            host=pg_config.host,
            port=pg_config.port,
            dbname=pg_config.database,
            user=pg_config.user,
            password=os.getenv("POSTGRES_PASSWORD", pg_config.password),
        )
        cur = conn.cursor()

        # Enable UUID extension
        logger.info("Enabling extensions...")
        cur.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
        cur.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm";')  # For text search

        # Create tables
        logger.info("Creating tables...")

        # 1. Documents table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                doc_id VARCHAR(255) NOT NULL,
                tenant_id VARCHAR(100) NOT NULL,
                source TEXT NOT NULL,
                content_hash VARCHAR(64) NOT NULL,
                file_size BIGINT,
                doc_type VARCHAR(50),
                state VARCHAR(50) NOT NULL DEFAULT 'new',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                indexed_at TIMESTAMP,
                vector_indexed BOOLEAN DEFAULT FALSE,
                keyword_indexed BOOLEAN DEFAULT FALSE,
                chunk_count INTEGER DEFAULT 0,
                error_message TEXT,
                metadata JSONB DEFAULT '{}',
                PRIMARY KEY (tenant_id, doc_id)
            );

            CREATE INDEX IF NOT EXISTS idx_documents_tenant_state
            ON documents(tenant_id, state);

            CREATE INDEX IF NOT EXISTS idx_documents_content_hash
            ON documents(tenant_id, content_hash);
        """)

        # 2. Index entries table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS index_entries (
                id SERIAL PRIMARY KEY,
                tenant_id VARCHAR(100) NOT NULL,
                doc_id VARCHAR(255) NOT NULL,
                index_type VARCHAR(20) NOT NULL,
                node_id VARCHAR(255) NOT NULL,
                chunk_index INTEGER NOT NULL,
                content_hash VARCHAR(64),
                indexed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                metadata JSONB DEFAULT '{}',
                FOREIGN KEY (tenant_id, doc_id) REFERENCES documents(tenant_id, doc_id) ON DELETE CASCADE,
                UNIQUE(tenant_id, doc_id, index_type, node_id)
            );

            CREATE INDEX IF NOT EXISTS idx_index_entries_lookup
            ON index_entries(tenant_id, doc_id, index_type);
        """)

        # 3. Keyword search table (using tsvector for full-text search)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS keyword_search (
                id SERIAL PRIMARY KEY,
                tenant_id VARCHAR(100) NOT NULL,
                doc_id VARCHAR(255) NOT NULL,
                node_id VARCHAR(255) NOT NULL,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                content_tsvector tsvector,
                metadata JSONB DEFAULT '{}',
                content_hash VARCHAR(64),
                indexed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(tenant_id, node_id)
            );

            CREATE INDEX IF NOT EXISTS idx_keyword_search_fts
            ON keyword_search USING GIN(content_tsvector);

            CREATE INDEX IF NOT EXISTS idx_keyword_search_doc
            ON keyword_search(tenant_id, doc_id);
        """)

        # 4. Fingerprints table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS fingerprints (
                id SERIAL PRIMARY KEY,
                tenant_id VARCHAR(100) NOT NULL,
                file_path TEXT NOT NULL,
                content_hash VARCHAR(64) NOT NULL,
                file_size BIGINT NOT NULL,
                last_modified TIMESTAMP NOT NULL,
                metadata JSONB DEFAULT '{}',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(tenant_id, file_path)
            );

            CREATE INDEX IF NOT EXISTS idx_fingerprints_lookup
            ON fingerprints(tenant_id, file_path);
        """)

        # 5. Jobs table (for new production jobs - test jobs not migrated)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                tenant_id VARCHAR(100) NOT NULL,
                job_type VARCHAR(50) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                doc_id VARCHAR(255),
                priority INTEGER DEFAULT 0,
                payload JSONB DEFAULT '{}',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                error_message TEXT,
                retry_count INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_jobs_status
            ON jobs(tenant_id, status, priority DESC, created_at);
        """)

        # 6. Schema version table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                description TEXT
            );

            INSERT INTO schema_version (version, description)
            VALUES (1, 'Initial schema with multi-tenant support')
            ON CONFLICT (version) DO NOTHING;
        """)

        # Create update trigger for documents
        cur.execute("""
            CREATE OR REPLACE FUNCTION update_updated_at_column()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = CURRENT_TIMESTAMP;
                RETURN NEW;
            END;
            $$ language 'plpgsql';

            DROP TRIGGER IF EXISTS update_documents_updated_at ON documents;

            CREATE TRIGGER update_documents_updated_at
            BEFORE UPDATE ON documents
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """)

        # Create text search trigger for keyword_search
        cur.execute("""
            CREATE OR REPLACE FUNCTION update_content_tsvector()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.content_tsvector = to_tsvector('english', NEW.content);
                RETURN NEW;
            END;
            $$ language 'plpgsql';

            DROP TRIGGER IF EXISTS update_keyword_search_tsvector ON keyword_search;

            CREATE TRIGGER update_keyword_search_tsvector
            BEFORE INSERT OR UPDATE ON keyword_search
            FOR EACH ROW EXECUTE FUNCTION update_content_tsvector();
        """)

        # Commit changes
        conn.commit()
        logger.info("✓ All tables created successfully")

        # Create row-level security policies (optional but recommended)
        logger.info("Setting up row-level security...")
        cur.execute("""
            -- Enable RLS on all tables
            ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
            ALTER TABLE index_entries ENABLE ROW LEVEL SECURITY;
            ALTER TABLE keyword_search ENABLE ROW LEVEL SECURITY;
            ALTER TABLE fingerprints ENABLE ROW LEVEL SECURITY;
            ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;

            -- Create application role if it doesn't exist
            DO $$ BEGIN
                CREATE ROLE rag_app_role;
            EXCEPTION WHEN duplicate_object THEN
                RAISE NOTICE 'Role rag_app_role already exists';
            END $$;

            -- Grant permissions to application role
            GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO rag_app_role;
            GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO rag_app_role;

            -- Create policies for tenant isolation (using session variable)
            DROP POLICY IF EXISTS tenant_isolation_documents ON documents;
            CREATE POLICY tenant_isolation_documents ON documents
                FOR ALL TO rag_app_role
                USING (tenant_id = current_setting('app.current_tenant', true));

            DROP POLICY IF EXISTS tenant_isolation_index_entries ON index_entries;
            CREATE POLICY tenant_isolation_index_entries ON index_entries
                FOR ALL TO rag_app_role
                USING (tenant_id = current_setting('app.current_tenant', true));

            DROP POLICY IF EXISTS tenant_isolation_keyword_search ON keyword_search;
            CREATE POLICY tenant_isolation_keyword_search ON keyword_search
                FOR ALL TO rag_app_role
                USING (tenant_id = current_setting('app.current_tenant', true));

            DROP POLICY IF EXISTS tenant_isolation_fingerprints ON fingerprints;
            CREATE POLICY tenant_isolation_fingerprints ON fingerprints
                FOR ALL TO rag_app_role
                USING (tenant_id = current_setting('app.current_tenant', true));

            DROP POLICY IF EXISTS tenant_isolation_jobs ON jobs;
            CREATE POLICY tenant_isolation_jobs ON jobs
                FOR ALL TO rag_app_role
                USING (tenant_id = current_setting('app.current_tenant', true));
        """)

        conn.commit()
        logger.info("✓ Row-level security configured")

        cur.close()
        conn.close()

        logger.info("\n✅ PostgreSQL setup completed successfully!")
        logger.info(f"Database: {pg_config.database}")
        logger.info(f"Default tenant: {pg_config.default_tenant_id}")

    except Exception as e:
        logger.error(f"Failed to set up database: {e}")
        sys.exit(1)


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Set up PostgreSQL for RAG Lab")
    parser.add_argument(
        "--config",
        default="config_postgres.yaml",
        help="Configuration file (default: config_postgres.yaml)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop existing tables and recreate (WARNING: destroys data)",
    )

    args = parser.parse_args()

    # Load configuration
    if not Path(args.config).exists():
        logger.error(f"Configuration file not found: {args.config}")
        sys.exit(1)

    config = PipelineConfig.from_yaml(args.config)

    if args.reset:
        response = input("⚠️  This will DELETE ALL DATA. Are you sure? (yes/no): ")
        if response.lower() != "yes":
            logger.info("Cancelled")
            sys.exit(0)

        # Drop tables
        logger.warning("Dropping existing tables...")
        # TODO: Implement table dropping

    # Run setup
    setup_database(config)


if __name__ == "__main__":
    main()

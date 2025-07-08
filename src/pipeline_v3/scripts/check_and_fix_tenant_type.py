#!/usr/bin/env python3
"""
Check and fix tenant_id type issues in PostgreSQL.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import psycopg

from src.pipeline_v3.utils.common_utils import logger


def check_and_fix_tenant_types():
    """Check tenant_id column types and fix if needed."""
    logger.info("=== Checking Tenant ID Column Types ===")

    # Connect to PostgreSQL
    conn = psycopg.connect(
        host="localhost",
        port=5432,
        dbname="rag_lab",
        user="rag_user",
        password=os.getenv("POSTGRES_PASSWORD", "rag_dev_password"),
    )

    try:
        with conn.cursor() as cur:
            # Check column types in all tables
            tables = [
                ("registry", "documents"),
                ("registry", "index_entries"),
                ("search", "keyword_search"),
                ("search", "doc_metadata"),
                ("fingerprints", "fingerprints"),
                ("jobs", "jobs"),
                ("jobs", "job_metadata"),
            ]

            for schema, table in tables:
                try:
                    cur.execute(
                        """
                        SELECT column_name, data_type, character_maximum_length
                        FROM information_schema.columns
                        WHERE table_schema = %s AND table_name = %s AND column_name = 'tenant_id'
                    """,
                        (schema, table),
                    )

                    result = cur.fetchone()
                    if result:
                        col_name, data_type, max_length = result
                        logger.info(f"{schema}.{table}.tenant_id: {data_type}({max_length})")

                        # If it's varchar, we need to ensure we're passing strings, not UUIDs
                        if data_type == "character varying":
                            logger.warning(
                                f"  -> Table {schema}.{table} uses VARCHAR for tenant_id"
                            )
                except Exception as e:
                    logger.error(f"Error checking {schema}.{table}: {e}")

            logger.info("\nSolution: PostgreSQL adapters should pass tenant_id as string, not UUID")

    finally:
        conn.close()


if __name__ == "__main__":
    check_and_fix_tenant_types()

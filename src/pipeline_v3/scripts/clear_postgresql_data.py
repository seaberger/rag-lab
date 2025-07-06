#!/usr/bin/env python3
"""
Clear all data from PostgreSQL for a fresh start.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import psycopg

from src.pipeline_v3.utils.common_utils import logger

TENANT_ID = "f47ac10b-58cc-4372-a567-0e02b2c3d479"  # lmc-dev tenant


def clear_postgresql_data():
    """Clear all data from PostgreSQL tables."""
    logger.info("=== Clearing PostgreSQL Data ===")

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
            # Clear tables in correct order (respecting foreign keys)
            tables = [
                ("index_entries", "index entries"),
                ("documents", "documents"),
                ("keyword_search", "keyword search entries"),
                ("doc_metadata", "document metadata"),
                ("fingerprints", "fingerprints"),
                ("jobs", "jobs"),
                ("job_metadata", "job metadata"),
            ]

            for table, description in tables:
                try:
                    cur.execute(f"DELETE FROM {table} WHERE tenant_id = %s", (TENANT_ID,))
                    count = cur.rowcount
                    logger.info(f"Deleted {count} {description}")
                except Exception as e:
                    logger.warning(f"Could not clear {table}: {e}")

            conn.commit()
            logger.info("✓ PostgreSQL data cleared")

    finally:
        conn.close()


def clear_qdrant_data():
    """Clear all data from Qdrant server."""
    logger.info("\n=== Clearing Qdrant Data ===")

    import qdrant_client

    try:
        client = qdrant_client.QdrantClient(host="localhost", port=6333)

        # Delete collection
        collections = [c.name for c in client.get_collections().collections]
        if "datasheets_v3" in collections:
            client.delete_collection("datasheets_v3")
            logger.info("✓ Deleted datasheets_v3 collection")

            # Recreate empty collection
            from qdrant_client.models import Distance, VectorParams

            client.create_collection(
                collection_name="datasheets_v3",
                vectors_config=VectorParams(
                    size=1536,  # OpenAI embedding size
                    distance=Distance.COSINE,
                ),
            )
            logger.info("✓ Recreated empty datasheets_v3 collection")
        else:
            logger.info("Collection datasheets_v3 not found")

    except Exception as e:
        logger.error(f"Error clearing Qdrant: {e}")


if __name__ == "__main__":
    clear_postgresql_data()
    clear_qdrant_data()
    logger.info("\n✓ All data cleared. Ready for fresh document processing!")

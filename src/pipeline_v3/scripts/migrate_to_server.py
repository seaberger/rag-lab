#!/usr/bin/env python3
"""
Migration script to move from local Qdrant to server mode.

This script helps migrate existing documents from local Qdrant storage
to a Qdrant server instance.
"""

import argparse
import sys
from pathlib import Path

# Add parent directories to path
sys.path.append(str(Path(__file__).parent.parent))
sys.path.append(str(Path(__file__).parent.parent.parent))

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from utils.common_utils import logger


class QdrantMigrator:
    """Migrate data from local Qdrant to server."""

    def __init__(self, local_path: str, server_host: str, server_port: int):
        """Initialize migrator with local and server connections."""
        self.local_path = local_path
        self.server_host = server_host
        self.server_port = server_port

        # Initialize clients
        self.local_client = None
        self.server_client = None

    def connect(self) -> bool:
        """Establish connections to local and server Qdrant."""
        try:
            # Connect to local Qdrant
            logger.info(f"Connecting to local Qdrant at: {self.local_path}")
            self.local_client = QdrantClient(path=self.local_path)

            # Connect to server Qdrant
            logger.info(f"Connecting to Qdrant server at: {self.server_host}:{self.server_port}")
            self.server_client = QdrantClient(
                host=self.server_host,
                port=self.server_port,
            )

            return True

        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            return False

    def list_collections(self) -> list[str]:
        """List collections in local Qdrant."""
        try:
            collections = self.local_client.get_collections()
            return [col.name for col in collections.collections]
        except Exception as e:
            logger.error(f"Failed to list collections: {e}")
            return []

    def migrate_collection(self, collection_name: str, batch_size: int = 100) -> bool:
        """Migrate a single collection from local to server."""
        try:
            logger.info(f"Migrating collection: {collection_name}")

            # Get collection info from local
            local_info = self.local_client.get_collection(collection_name)
            vector_size = local_info.config.params.vectors.size

            # Check if collection exists on server
            server_collections = [
                col.name for col in self.server_client.get_collections().collections
            ]

            if collection_name in server_collections:
                logger.warning(f"Collection {collection_name} already exists on server")
                response = input("Overwrite? (y/N): ")
                if response.lower() != "y":
                    return False

                # Delete existing collection
                self.server_client.delete_collection(collection_name)

            # Create collection on server
            logger.info(f"Creating collection on server with vector size: {vector_size}")
            self.server_client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=vector_size,
                    distance=Distance.COSINE,
                ),
            )

            # Migrate data in batches
            offset = None
            total_migrated = 0

            while True:
                # Scroll through local collection
                records, next_offset = self.local_client.scroll(
                    collection_name=collection_name,
                    offset=offset,
                    limit=batch_size,
                    with_payload=True,
                    with_vectors=True,
                )

                if not records:
                    break

                # Upload to server
                self.server_client.upsert(
                    collection_name=collection_name,
                    points=records,
                )

                total_migrated += len(records)
                logger.info(f"Migrated {total_migrated} points...")

                offset = next_offset
                if offset is None:
                    break

            logger.info(f"✓ Successfully migrated {total_migrated} points")
            return True

        except Exception as e:
            logger.error(f"Failed to migrate collection {collection_name}: {e}")
            return False

    def verify_migration(self, collection_name: str) -> bool:
        """Verify that migration was successful."""
        try:
            local_info = self.local_client.get_collection(collection_name)
            server_info = self.server_client.get_collection(collection_name)

            local_count = local_info.points_count
            server_count = server_info.points_count

            logger.info(f"Local points: {local_count}")
            logger.info(f"Server points: {server_count}")

            if local_count == server_count:
                logger.info("✓ Migration verified successfully")
                return True
            else:
                logger.error("✗ Point counts don't match!")
                return False

        except Exception as e:
            logger.error(f"Failed to verify migration: {e}")
            return False


def main():
    """Main migration function."""
    parser = argparse.ArgumentParser(description="Migrate Qdrant from local to server mode")
    parser.add_argument(
        "--local-path",
        default="./qdrant_data_v3",
        help="Path to local Qdrant storage",
    )
    parser.add_argument(
        "--server-host",
        default="localhost",
        help="Qdrant server host",
    )
    parser.add_argument(
        "--server-port",
        type=int,
        default=6333,
        help="Qdrant server port",
    )
    parser.add_argument(
        "--collection",
        help="Specific collection to migrate (default: all)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Batch size for migration",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify migration after completion",
    )

    args = parser.parse_args()

    # Create migrator
    migrator = QdrantMigrator(
        local_path=args.local_path,
        server_host=args.server_host,
        server_port=args.server_port,
    )

    # Connect to both instances
    if not migrator.connect():
        logger.error("Failed to establish connections")
        return 1

    # Get collections to migrate
    if args.collection:
        collections = [args.collection]
    else:
        collections = migrator.list_collections()
        if not collections:
            logger.warning("No collections found to migrate")
            return 0

    logger.info(f"Collections to migrate: {collections}")

    # Migrate each collection
    success_count = 0
    for collection in collections:
        if migrator.migrate_collection(collection, args.batch_size):
            success_count += 1

            if args.verify:
                migrator.verify_migration(collection)

    logger.info(f"\nMigration complete: {success_count}/{len(collections)} collections migrated")

    return 0 if success_count == len(collections) else 1


if __name__ == "__main__":
    sys.exit(main())

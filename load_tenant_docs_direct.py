#!/usr/bin/env python3
"""
Load documents directly into tenants bypassing the CLI.
This uses the core components directly.
"""

import os
import sys
from pathlib import Path

# Set up environment
os.environ["POSTGRES_PASSWORD"] = "rag_dev_password"

# Add to Python path
sys.path.insert(0, str(Path(__file__).parent))

# Now import after path is set
import time

from src.pipeline_v3.core.parsers import DatasheetParser, DocumentMode
from src.pipeline_v3.core.postgres_registry import PostgreSQLDocumentRegistry
from src.pipeline_v3.processing.chunker import DocumentChunker
from src.pipeline_v3.processing.embedder import DocumentEmbedder
from src.pipeline_v3.storage.postgres_keyword import PostgreSQLKeywordIndex
from src.pipeline_v3.storage.vector_store import VectorStore
from src.pipeline_v3.utils.common_utils import logger
from src.pipeline_v3.utils.config import PipelineConfig


def process_document_for_tenant(doc_path: str, tenant_id: str, tenant_name: str):
    """Process a single document for a specific tenant."""

    print(f"\n📄 Processing {Path(doc_path).name} for {tenant_name} tenant")
    print(f"   Tenant ID: {tenant_id}")

    # Load config
    config = PipelineConfig()

    # Create tenant-specific components
    registry = PostgreSQLDocumentRegistry(config=config, tenant_id=tenant_id)
    vector_store = VectorStore(config=config, tenant_id=tenant_id)
    keyword_index = PostgreSQLKeywordIndex(config=config, tenant_id=tenant_id)

    # Parser components
    parser = DatasheetParser(config=config)
    chunker = DocumentChunker(config=config)
    embedder = DocumentEmbedder(config=config)

    try:
        # 1. Register document
        print("   1️⃣ Registering document...")
        doc_id = registry.register_document(
            source=doc_path,
            content_hash=f"hash_{Path(doc_path).stem}_{tenant_id[:8]}",
            size=Path(doc_path).stat().st_size,
            modified_time=Path(doc_path).stat().st_mtime,
            metadata={"tenant": tenant_name, "document_type": "datasheet"},
        )
        print(f"      ✓ Document ID: {doc_id}")

        # 2. Parse document
        print("   2️⃣ Parsing with OpenAI Vision API...")
        start_time = time.time()
        parsed_result = parser.parse(
            file_path=doc_path, mode=DocumentMode.DATASHEET, with_keywords=True
        )
        parse_time = time.time() - start_time
        print(f"      ✓ Parsed in {parse_time:.1f}s")
        print(f"      ✓ Extracted {len(parsed_result.metadata.get('keywords', []))} keywords")

        # 3. Chunk document
        print("   3️⃣ Creating chunks...")
        chunks = chunker.chunk(parsed_result)
        print(f"      ✓ Created {len(chunks)} chunks")

        # 4. Create embeddings
        print("   4️⃣ Generating embeddings...")
        start_time = time.time()
        embeddings = embedder.embed(chunks)
        embed_time = time.time() - start_time
        print(f"      ✓ Generated {len(embeddings)} embeddings in {embed_time:.1f}s")

        # 5. Store in vector database
        print("   5️⃣ Storing in Qdrant...")
        vector_store.store(doc_id=doc_id, chunks=chunks, embeddings=embeddings, source=doc_path)
        print(f"      ✓ Stored in collection: tenant_{tenant_id}")

        # 6. Index for keyword search
        print("   6️⃣ Indexing for keyword search...")
        keyword_index.index_nodes(
            nodes=chunks,
            doc_id=doc_id,
            source=doc_path,
            keywords=parsed_result.metadata.get("keywords", []),
        )
        print(f"      ✓ Indexed {len(chunks)} chunks")

        # 7. Update document state
        registry.update_document_state(
            doc_id=doc_id,
            state="INDEXED",
            chunk_count=len(chunks),
            vector_indexed=True,
            keyword_indexed=True,
        )

        print(f"\n   ✅ Successfully processed document for {tenant_name}!")
        return True

    except Exception as e:
        logger.error(f"Failed to process document for {tenant_name}: {e}", exc_info=True)
        print(f"\n   ❌ Error: {e!s}")

        # Update document state to failed
        try:
            registry.update_document_state(doc_id=doc_id, state="FAILED", error_message=str(e))
        except:
            pass

        return False


def main():
    """Load one datasheet into each tenant."""

    # Find datasheet PDFs
    sample_dir = Path("data/sample_docs")
    ds_pdfs = sorted(list(sample_dir.glob("*ds*.pdf")) + list(sample_dir.glob("*DS*.pdf")))

    if len(ds_pdfs) < 3:
        print(f"❌ Need at least 3 datasheet PDFs, found {len(ds_pdfs)}")
        return

    print("Found datasheet PDFs:")
    for i, pdf in enumerate(ds_pdfs[:3]):
        print(f"  {i + 1}. {pdf.name}")

    # Tenant configurations
    tenants = [
        {
            "name": "lmc",
            "tenant_id": "51b272e9-be33-4b63-9afd-7c1ca9d1b403",
            "doc": str(ds_pdfs[0]),
        },
        {
            "name": "cellx",
            "tenant_id": "b7a1ccc4-e28e-4967-ad7a-f8f8cfcf89dd",
            "doc": str(ds_pdfs[1]),
        },
        {
            "name": "matrix",
            "tenant_id": "081f2c7d-20be-4fc6-b8e2-113b9629db8e",
            "doc": str(ds_pdfs[2]),
        },
    ]

    print("\n" + "=" * 60)
    print("Loading Documents into Tenants")
    print("=" * 60)

    # Process each tenant
    success_count = 0
    for tenant in tenants:
        if process_document_for_tenant(tenant["doc"], tenant["tenant_id"], tenant["name"]):
            success_count += 1

    print("\n" + "=" * 60)
    print(f"Loaded {success_count}/3 documents successfully")
    print("=" * 60)

    if success_count == 3:
        print("\n✅ All documents loaded successfully!")
        print("\nNext steps:")
        print("  1. Run isolation test: python test_rls_isolation.py")
        print("  2. Test search: python test_tenant_search.py")
    else:
        print("\n⚠️  Some documents failed to load")


if __name__ == "__main__":
    main()

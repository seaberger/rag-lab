#!/usr/bin/env python3
"""
Load sample documents into each tenant for RLS testing.
Uses the actual pipeline to test parsing, embedding, and storage.
"""

import os
import sys
import time
from pathlib import Path

# Add pipeline to path
sys.path.append(str(Path(__file__).parent))

# Set environment
os.environ["POSTGRES_PASSWORD"] = "rag_dev_password"
os.environ["PYTHONPATH"] = str(Path(__file__).parent)

from src.pipeline_v3.core.postgres_registry import PostgreSQLDocumentRegistry

# Job manager not needed for direct processing
from src.pipeline_v3.pipeline.enhanced_core import EnhancedPipeline
from src.pipeline_v3.utils.common_utils import logger
from src.pipeline_v3.utils.config import PipelineConfig


def load_documents_for_tenants():
    """Load sample documents into each tenant."""

    # Load configuration
    config = PipelineConfig()

    # Find all 'ds' (datasheet) PDFs in sample_docs
    sample_dir = Path("data/sample_docs")
    ds_pdfs = list(sample_dir.glob("*ds*.pdf")) + list(sample_dir.glob("*DS*.pdf"))

    if len(ds_pdfs) < 3:
        print(f"❌ Need at least 3 datasheet PDFs, found {len(ds_pdfs)}")
        return

    # Sort for consistent assignment
    ds_pdfs.sort()

    print(f"Found {len(ds_pdfs)} datasheet PDFs:")
    for pdf in ds_pdfs:
        print(f"  - {pdf.name}")

    # Tenant configurations - assign one datasheet to each
    tenants = [
        {
            "name": "lmc",
            "tenant_id": "51b272e9-be33-4b63-9afd-7c1ca9d1b403",
            "doc": str(ds_pdfs[0]),  # First datasheet
        },
        {
            "name": "cellx",
            "tenant_id": "b7a1ccc4-e28e-4967-ad7a-f8f8cfcf89dd",
            "doc": str(ds_pdfs[1]),  # Second datasheet
        },
        {
            "name": "matrix",
            "tenant_id": "081f2c7d-20be-4fc6-b8e2-113b9629db8e",
            "doc": str(ds_pdfs[2]),  # Third datasheet
        },
    ]

    print("\nLoading Sample Documents for Each Tenant")
    print("=" * 60)

    # Process each tenant
    for tenant in tenants:
        print(f"\n📁 Processing for {tenant['name'].upper()} tenant")
        print(f"   Tenant ID: {tenant['tenant_id']}")
        print(f"   Document: {Path(tenant['doc']).name}")

        # Create pipeline with tenant context
        pipeline = EnhancedPipeline(config=config, tenant_id=tenant["tenant_id"])

        doc_path = tenant["doc"]

        if not Path(doc_path).exists():
            print(f"  ❌ Document not found: {doc_path}")
            continue

        try:
            # Add document to processing queue
            print("\n  1️⃣ Adding to processing queue...")
            result = pipeline.add_document(
                source=doc_path,
                mode="datasheet",  # Use datasheet mode for technical PDFs
                with_keywords=True,  # Enable keyword extraction
            )

            job_id = result.get("job_id")
            print(f"     ✓ Created job: {job_id}")

            # Process the document through the full pipeline
            print("\n  2️⃣ Processing document...")
            print("     - Parsing PDF with OpenAI Vision API")
            print("     - Extracting keywords")
            print("     - Creating embeddings")
            print("     - Storing in PostgreSQL and Qdrant")

            # Process synchronously for testing
            start_time = time.time()
            pipeline.process_single_document(doc_path)
            elapsed = time.time() - start_time

            print(f"\n  ✅ Document processed successfully in {elapsed:.1f}s")

            # Verify it was stored
            registry = PostgreSQLDocumentRegistry(config=config, tenant_id=tenant["tenant_id"])

            docs = registry.list_documents()
            if docs:
                doc = docs[-1]  # Get the most recent
                print("\n  3️⃣ Verification:")
                print(f"     - Document ID: {doc.doc_id}")
                print(f"     - State: {doc.state}")
                print(f"     - Chunks: {doc.chunk_count}")
                print(f"     - Vector indexed: {doc.vector_indexed}")
                print(f"     - Keyword indexed: {doc.keyword_indexed}")

        except Exception as e:
            print(f"\n  ❌ Error: {e!s}")
            logger.error(f"Failed to process {doc_path} for tenant {tenant['name']}", exc_info=True)

    print("\n" + "=" * 60)
    print("Document Loading Summary")
    print("=" * 60)

    # Show summary for each tenant
    for tenant in tenants:
        registry = PostgreSQLDocumentRegistry(config=config, tenant_id=tenant["tenant_id"])

        docs = registry.list_documents()
        print(f"\n{tenant['name'].upper()} (Tenant ID: {tenant['tenant_id'][:8]}...)")
        print(f"  Documents: {len(docs)}")

        for doc in docs:
            print(f"    - {doc.source} (State: {doc.state}, Chunks: {doc.chunk_count})")

    print("\n✅ Document loading complete!")
    print("\n📝 Next Steps:")
    print("   1. Run RLS isolation tests: python test_rls_isolation.py")
    print("   2. Test search functionality per tenant")
    print("   3. Verify API key authentication")


if __name__ == "__main__":
    load_documents_for_tenants()

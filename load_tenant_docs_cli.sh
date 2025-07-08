#!/bin/bash
# Load one datasheet into each tenant using the CLI

# Set environment
export POSTGRES_PASSWORD=rag_dev_password
export PYTHONPATH=/Users/seanbergman/Repositories/rag_lab

echo "Loading Documents into Each Tenant"
echo "=================================="

# Find datasheet PDFs
DS_PDFS=(data/sample_docs/*ds*.pdf data/sample_docs/*DS*.pdf)

# Remove duplicates and sort
DS_PDFS=($(printf "%s\n" "${DS_PDFS[@]}" | sort -u))

echo "Found datasheet PDFs:"
for pdf in "${DS_PDFS[@]}"; do
    echo "  - $(basename "$pdf")"
done

# Tenant configurations
TENANTS=(
    "lmc:51b272e9-be33-4b63-9afd-7c1ca9d1b403"
    "cellx:b7a1ccc4-e28e-4967-ad7a-f8f8cfcf89dd"
    "matrix:081f2c7d-20be-4fc6-b8e2-113b9629db8e"
)

# Load one document per tenant
for i in "${!TENANTS[@]}"; do
    IFS=':' read -r name tenant_id <<< "${TENANTS[$i]}"
    doc="${DS_PDFS[$i]}"

    echo ""
    echo "Loading document for $name tenant:"
    echo "  Tenant ID: $tenant_id"
    echo "  Document: $(basename "$doc")"

    # Use CLI to add document with tenant context
    TENANT_ID=$tenant_id uv run python -m src.pipeline_v3.cli_main add "$doc" \
        --mode datasheet \
        --with-keywords \
        --force

    if [ $? -eq 0 ]; then
        echo "✓ Successfully loaded document for $name"
    else
        echo "✗ Failed to load document for $name"
    fi
done

echo ""
echo "=================================="
echo "Document loading complete!"
echo ""
echo "To verify isolation, run:"
echo "  python test_rls_isolation.py"

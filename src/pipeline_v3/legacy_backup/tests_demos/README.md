# Tests and Demos Backup

This folder contains test files and demos that were used during development but are not needed for production use.

## Files Moved:
- `demo_cli.py` - CLI demonstration script
- `search_demo.py` - Search functionality demo
- `detailed_search_test.py` - Search testing
- `integration_test.py` - Integration testing
- `quick_integration_test.py` - Quick integration tests
- `real_doc_search_test.py` - Real document search tests
- `test_cli.py` - CLI testing script
- `test_cli_simple.py` - Simple CLI tests
- `test_foundation.py` - Foundation testing
- `test_phase1.py` - Phase 1 testing
- `test_phase2.py` - Phase 2 testing
- `verify_real_search.py` - Search verification

## Production Testing:
For current testing, use the main CLI:
```bash
uv run python -m src.pipeline_v3.cli_main add data/sample_docs/labmax-touch-ds.pdf --mode datasheet
```

These files are kept for reference and may be removed in future versions.

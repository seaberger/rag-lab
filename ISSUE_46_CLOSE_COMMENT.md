# Issue #46: Close Comment - Timeout Workaround

## Resolution: Workaround Available

After investigation, the timeout issue is caused by the **shell/bash default timeout of 2 minutes**, not the OpenAI API or Python code. This is a fundamental limitation when running commands through the shell.

### Root Cause
- **Shell timeout**: 2 minutes (120 seconds) default
- **PDF processing time**: ~30-45 seconds per page with OpenAI Vision API
- **Result**: Commands timeout after processing only 3-4 pages

### Workaround Solution

For documents that need more than 2 minutes to process, use the `--timeout` parameter:

```bash
# Extend timeout to 10 minutes for a 20-page document
uv run python -m src.pipeline_v3.cli_main add large_document.pdf --timeout 600

# Or process specific page ranges
uv run python -m src.pipeline_v3.cli_main add large_document.pdf --pages 1-10
```

### Updated Documentation

The following documentation has been updated with the timeout workaround:
- ✅ `QUEUE_SYSTEM_GUIDE.md` - Added timeout workaround section
- ✅ `BATCH_PROCESSING_GUIDE.md` - Updated decision matrix with timeout option
- ✅ `API_HARDENING.md` - Added shell vs API timeout explanation

### Recommendations

1. **For small documents (1-3 pages)**: Use direct CLI
2. **For medium documents (4-20 pages)**: Use `--timeout` parameter OR queue system
3. **For large documents (20+ pages)**: Always use queue system
4. **For production**: Always use queue system for reliability

### Future Enhancement

Created **Issue #47** for OpenAI Batch API integration, which would provide:
- 50% cost reduction on tokens
- No timeout limitations
- Better suited for bulk processing

### Closing Notes

The timeout workaround successfully addresses the immediate need for processing larger documents via direct CLI. However, the queue system remains the recommended approach for production workloads due to its superior reliability, monitoring, and error recovery capabilities.

**Status**: Closed with workaround
**Workaround**: Use `--timeout` parameter to extend shell timeout
**Long-term solution**: Queue system or Batch API (Issue #47)
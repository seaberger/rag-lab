# Issue #11: Configurable Timeout Handling

## Overview

Implemented configurable timeout handling for document processing, especially important for large PDF documents with many pages.

## Implementation Details

### 1. Configuration Updates

Added timeout settings to `PipelineConfig`:
- `pipeline.timeout_per_page`: Seconds per PDF page (default: 30)
- `pipeline.timeout_base`: Base timeout in seconds (default: 60)
- `openai.timeout_per_page`: API-specific timeout per page
- `openai.timeout_base`: API-specific base timeout

### 2. Page-Based Timeout Calculation

The system now calculates timeouts dynamically based on page count:
```python
timeout = base_timeout + (page_count * timeout_per_page)
```

For example:
- 5-page document: 210s (3.5 minutes)
- 20-page document: 660s (11 minutes)
- 100-page document: 3060s (51 minutes)

### 3. CLI Parameters

Added new CLI parameters for timeout control:
```bash
# Override total timeout
uv run python -m src.pipeline_v3.cli_main add document.pdf --timeout 1800

# Override per-page timeout
uv run python -m src.pipeline_v3.cli_main add document.pdf --timeout-per-page 45

# Both can be used together
uv run python -m src.pipeline_v3.cli_main add large_catalog.pdf --timeout 7200 --timeout-per-page 40
```

### 4. Enhanced Error Messages

When a timeout occurs, the system provides helpful information:
- Reports the number of pages in the document
- Suggests using --timeout or --timeout-per-page parameters
- Shows the timeout duration that was exceeded

## Usage Examples

### Processing Large Documents

For a 150-page catalog:
```bash
# Default would timeout at ~4560s (76 minutes)
# Increase per-page timeout for complex documents
uv run python -m src.pipeline_v3.cli_main add catalog.pdf --timeout-per-page 40

# Or set explicit total timeout
uv run python -m src.pipeline_v3.cli_main add catalog.pdf --timeout 7200  # 2 hours
```

### Batch Processing with Timeouts

```bash
# Process multiple large documents with custom timeout
uv run python -m src.pipeline_v3.cli_main add "docs/*.pdf" --timeout-per-page 35 --workers 2
```

## Technical Changes

1. **parsers.py**:
   - `_pdf_to_data_uris()` now returns page count
   - Timeout calculation in `vision_parse_datasheet()` and `vision_parse_generic()`
   - Pass timeout to retry decorator

2. **common_utils.py**:
   - Enhanced `retry_api_call` decorator with timeout support
   - Proper async timeout handling with `asyncio.wait_for`

3. **enhanced_core.py**:
   - Catch TimeoutError specifically
   - Provide helpful error messages with page count
   - Use configurable batch timeout

4. **cli/management.py**:
   - Added --timeout and --timeout-per-page arguments
   - Apply timeout overrides to config

## Default Timeout Values

- Base timeout: 60 seconds
- Per-page timeout: 30 seconds
- Batch processing timeout: 300 seconds (5 minutes)

These defaults work well for most documents but can be adjusted for:
- Complex technical documents (increase per-page)
- Simple text-heavy documents (decrease per-page)
- Very large documents (increase total timeout)

## Error Handling

When a timeout occurs:
1. The system logs the timeout with duration
2. Reports document page count if available
3. Suggests CLI parameters to increase limits
4. Preserves the error for proper handling upstream

## Future Enhancements

- Consider adaptive timeout based on document complexity
- Add progress callbacks during long operations
- Implement partial processing for very large documents
- Add timeout configuration to config.yaml
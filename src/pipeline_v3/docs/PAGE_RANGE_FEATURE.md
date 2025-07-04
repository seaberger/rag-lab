# Page Range Selection Feature

## Overview

The Page Range Selection feature allows you to process specific pages from PDF documents instead of processing the entire document. This is particularly useful for:

- **Testing large documents** progressively (e.g., test pages 1-10 before processing all 150 pages)
- **Processing specific sections** of documents (e.g., only the specification pages)
- **Cost optimization** by avoiding unnecessary API calls for irrelevant pages
- **Faster iteration** during development and testing

## Usage

### Basic Syntax

Add the `--pages` argument to any document processing command:

```bash
# Process pages 1 through 5
uv run python -m src.pipeline_v3.cli_main add document.pdf --pages "1-5"

# Process specific pages
uv run python -m src.pipeline_v3.cli_main add document.pdf --pages "1,3,5,7"

# Process multiple ranges
uv run python -m src.pipeline_v3.cli_main add document.pdf --pages "1-3,10-15,20"

# Process from page 10 to the end (requires knowing total pages)
uv run python -m src.pipeline_v3.cli_main add document.pdf --pages "10-"
```

### Supported Formats

| Format | Example | Description |
|--------|---------|-------------|
| Single page | `"5"` | Process only page 5 |
| Range | `"1-10"` | Process pages 1 through 10 (inclusive) |
| List | `"1,3,5"` | Process pages 1, 3, and 5 |
| Multiple ranges | `"1-3,7-9"` | Process pages 1-3 and 7-9 |
| Mixed | `"1-3,5,10-15"` | Combine ranges and individual pages |
| Open-ended | `"10-"` | Process from page 10 to end of document |

### Examples with Real Documents

```bash
# Test the first few pages of a large catalog
uv run python -m src.pipeline_v3.cli_main add catalog.pdf --pages "1-5" --mode datasheet --with-keywords

# Process only the specification section (pages 40-60)
uv run python -m src.pipeline_v3.cli_main add manual.pdf --pages "40-60" --mode datasheet

# Skip introduction and process main content
uv run python -m src.pipeline_v3.cli_main add report.pdf --pages "10-50" --mode generic

# Process cover, TOC, and first chapter
uv run python -m src.pipeline_v3.cli_main add book.pdf --pages "1-3,10-25"
```

## Progress Monitoring

When processing pages, you'll see real-time progress updates:

```
📄 Processing page 40 (1/21)...
✅ Page 40 processed in 0.06s
📄 Processing page 41 (2/21)...
✅ Page 41 processed in 0.08s
...
```

This provides:
- Visual indication of current page being processed
- Progress counter (e.g., "2/21" means page 2 of 21 total pages to process)
- Processing time for each page
- Clear success/failure indicators

## Best Practices

### 1. Progressive Testing
Start with small page ranges when testing large documents:
```bash
# First test
--pages "1-2"     # Quick validation

# If successful, expand
--pages "1-10"    # Small sample

# Then larger ranges
--pages "1-50"    # Half the document

# Finally, full document (no --pages argument)
```

### 2. Optimal Range Sizes
- **For testing**: 1-10 pages
- **For production**: 5-20 pages per batch
- **API limitations**: Avoid ranges larger than 20-30 pages in single request

### 3. Combine with Other Features
Page ranges work seamlessly with all other CLI options:
```bash
# With keyword enhancement
--pages "10-20" --with-keywords

# With custom parsing mode
--pages "1-5" --mode datasheet

# With custom timeout
--pages "1-100" --timeout-per-page 45

# With batch processing
add "docs/*.pdf" --pages "1-3" --workers 3
```

### 4. Document Analysis Strategy
For large technical documents:
1. Process pages 1-5 (cover, TOC)
2. Identify specification sections from TOC
3. Process those specific page ranges
4. Skip appendices or irrelevant sections

## Technical Details

### Page Numbering
- Pages are **1-indexed** (first page is 1, not 0)
- Page numbers refer to the actual PDF pages
- Invalid page numbers are caught and reported

### Performance Characteristics
- **Page extraction**: ~0.05-0.08 seconds per page
- **Memory efficient**: Only selected pages are loaded
- **Cache-friendly**: Each page range can be cached separately

### Error Handling
The system validates page ranges and provides clear error messages:
- `"Page numbers [155, 156] exceed document length (152 pages)"`
- `"Invalid range format: 5-2"` (end before start)
- `"Page numbers must be positive, got: 0"`

## Implementation Architecture

### Core Components

1. **PageRangeParser** (`utils/page_range.py`)
   - Parses page specifications into page number lists
   - Validates ranges against document length
   - Provides human-readable formatting

2. **PageProgressMonitor** (`utils/page_range.py`)
   - Tracks page processing progress
   - Provides real-time status updates
   - Calculates processing statistics

3. **Enhanced PDF Processing** (`core/parsers.py`)
   - Modified `_pdf_to_data_uris()` to support page ranges
   - Optimized for both single-page and batch processing
   - Integrated progress monitoring

### Processing Flow

1. User specifies `--pages "10-20"`
2. CLI passes page_range to processing pipeline
3. PDF processor:
   - Validates page range against total document pages
   - Extracts only specified pages
   - Shows progress for each page
   - Sends only selected pages to OpenAI API
4. Rest of pipeline proceeds normally with reduced content

## Troubleshooting

### Common Issues

**Issue**: "Page range exceeds document length"
- **Solution**: Check total pages first: `pdfinfo document.pdf | grep Pages`

**Issue**: Processing times out with large ranges
- **Solution**: Use smaller ranges (10-20 pages max) or increase timeout

**Issue**: Missing important content
- **Solution**: Review document structure and adjust page ranges accordingly

### Tips for Large Documents

1. **Use progressive ranges**: Test with small ranges first
2. **Monitor API costs**: Fewer pages = lower costs
3. **Check extraction quality**: Ensure important data isn't split across pages
4. **Save successful ranges**: Document which pages contain valuable content

## Future Enhancements

Potential improvements being considered:
- Automatic page content detection (skip blank pages)
- Smart section detection (find "Specifications" automatically)
- Page preview mode (see what's on pages before processing)
- Batch page range templates for common document types

## Related Features

- **Progress Monitoring**: Real-time feedback during processing
- **Keyword Enhancement**: Use `--with-keywords` for better search
- **Document Modes**: Combine with `--mode datasheet` for technical docs
- **Batch Processing**: Page ranges work with multiple files

---

For more information, see:
- [USER_MANUAL.md](../USER_MANUAL.md) - Complete CLI reference
- [QUICK_REFERENCE.md](../QUICK_REFERENCE.md) - Common commands
- [API_HARDENING.md](./API_HARDENING.md) - Related reliability improvements

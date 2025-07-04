# Sample URLs for Testing

This file contains a collection of URLs that have been tested with Pipeline v3's URL batch processing feature. These URLs can be used for testing document processing, queue functionality, and batch operations.

## Coherent Inc. Documents

### Datasheets
1. [PowerMax-USB UV/VIS Power Sensors](https://www.coherent.com/content/dam/coherent/site/en/resources/datasheet/power-and-energy-measurement/powermax-usb-uv-vis-power-sensors-ds.pdf)
   - **Type**: Technical datasheet
   - **Processing mode**: `--mode datasheet`
   - **Features**: Model/part number extraction, 14 chunks when processed
   - **Last tested**: Successfully processed with keyword enhancement

### Application Notes & White Papers
2. [Understanding a Certificate of Calibration](https://www.coherent.com/content/dam/coherent/site/en/resources/laser-measurement-and-control-help-center/application-notes-and-white-papers/application-notes/understanding-a-certificate-of-calibration.pdf)
   - **Type**: Technical document/white paper
   - **Processing mode**: `--mode generic` or `--mode auto`
   - **Features**: Single chunk document, good for calibration content
   - **Last tested**: Successfully processed with keyword enhancement

## Testing Usage Examples

### Basic URL Processing
```bash
# Process single URL with datasheet mode
uv run python -m src.pipeline_v3.cli_main add "https://www.coherent.com/content/dam/coherent/site/en/resources/datasheet/power-and-energy-measurement/powermax-usb-uv-vis-power-sensors-ds.pdf" --mode datasheet --with-keywords

# Process single URL with generic mode
uv run python -m src.pipeline_v3.cli_main add "https://www.coherent.com/content/dam/coherent/site/en/resources/laser-measurement-and-control-help-center/application-notes-and-white-papers/application-notes/understanding-a-certificate-of-calibration.pdf" --mode generic --with-keywords
```

### Batch URL Processing
```bash
# Create batch file from these URLs
uv run python -m src.pipeline_v3.cli_main batch create-url-file \
  "https://www.coherent.com/content/dam/coherent/site/en/resources/datasheet/power-and-energy-measurement/powermax-usb-uv-vis-power-sensors-ds.pdf" \
  "https://www.coherent.com/content/dam/coherent/site/en/resources/laser-measurement-and-control-help-center/application-notes-and-white-papers/application-notes/understanding-a-certificate-of-calibration.pdf" \
  --output test_batch.json

# Process URLs from this file as batch
uv run python -m src.pipeline_v3.cli_main add dummy --url-file test_batch.json --with-keywords --mode auto --workers 2

# Test queue processing with these URLs
uv run python -m src.pipeline_v3.cli_main batch test-queue test_batch.json --workers 2 --with-keywords
```

### Search Testing
After processing these URLs, you can test search functionality:
```bash
# Search for PowerMax content
uv run python -m src.pipeline_v3.cli_main search "powermax sensor" --type hybrid --top-k 3

# Search for calibration content
uv run python -m src.pipeline_v3.cli_main search "calibration certificate" --type hybrid --top-k 3

# Search for model numbers
uv run python -m src.pipeline_v3.cli_main search "UV/VIS" --type keyword --top-k 2
```

## URL Validation Results

When processed through `batch validate-urls`, these URLs show:
- **Total URLs**: 2
- **Valid URLs**: 2
- **Invalid URLs**: 0
- **Duplicates**: 0
- **Domain**: www.coherent.com (2 documents)

## Performance Benchmarks

### Direct Batch Processing
- **Total documents**: 2
- **Processing time**: ~23 seconds with keyword enhancement
- **Success rate**: 100%
- **Chunks generated**: 15 total (14 + 1)

### Queue Processing
- **Jobs created**: 2
- **Queue processing time**: ~2.1 seconds
- **Success rate**: 100%
- **Workers used**: 2

## Notes for Future Testing

1. **Network Dependency**: These URLs require internet access to test
2. **File Size**: Both PDFs are reasonably sized for testing (500KB-750KB)
3. **Content Variety**: Mix of technical datasheet and general document content
4. **Keyword Enhancement**: Both work well with --with-keywords flag
5. **Model Extraction**: PowerMax datasheet extracts model/part number pairs
6. **Search Quality**: Both documents provide good search result variety

## Adding New Test URLs

When adding new URLs to this collection:
1. Test the URL manually first to ensure it's accessible
2. Note the document type and recommended processing mode
3. Document any special features (model extraction, tables, etc.)
4. Update the batch processing examples if needed
5. Verify the URL works with all three processing modes (datasheet, generic, auto)

---

*Last updated: July 2, 2025*
*Pipeline v3 URL Batch Processing Feature*

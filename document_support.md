# Expanded Document Support

## Comprehensive Document Support

Our system supports a wide range of document types and processing options with powerful directory scanning capabilities:

### Supported Document Types

**PDFs** - Technical documents, datasheets, reports with page-range selection
```bash
python cli_main.py add document.pdf --pages "1-10,15-20"
```

**Word Documents** - .docx/.doc files with structure and table preservation
```bash
python cli_main.py add report.docx --processing-options keywords
```

**PowerPoint Presentations** - .pptx/.ppt with slide-by-slide extraction
```bash
python cli_main.py add presentation.pptx --document-type auto
```

**Markdown Files** - Native support with structure preservation
```bash
python cli_main.py add documentation.md --processing-options structured
```

**URLs** - Direct web content processing with automatic extraction
```bash
python cli_main.py add https://example.com/datasheet.pdf
```

### Directory Processing

**Recursive Scanning** - Deep directory traversal with pattern filtering
```bash
python cli_main.py add data/docs --recursive --include-pattern "*.pdf,*.docx"
```

**Include Patterns** - Process only specific file types
```bash
python cli_main.py add data/docs --include-pattern "*.pdf" --include-pattern "*.md"
```

**Exclude Patterns** - Skip unwanted files and directories
```bash
python cli_main.py add data/docs --recursive --exclude-pattern "**/test/**,**/temp/**"
```

**Dry Run Preview** - Preview files before processing
```bash
python cli_main.py add data/docs --recursive --dry-run --include-pattern "*.pdf"
```

### Advanced Features

**Page Range Selection** - Process specific pages from PDFs
```bash
python cli_main.py add large_document.pdf --pages "1-5,10,15-20,50-"
```

**Batch URL Processing** - Process multiple URLs from file
```bash
python cli_main.py add dummy --url-file urls.json --workers 3
```

**Combined Processing** - Mix files, URLs, and directories
```bash
python cli_main.py add doc.pdf https://example.com/page.html data/docs --recursive
```

## Microsoft Office Documents (NEW)

### Word Documents (.docx, .doc)
- **Full Text Extraction**: Preserves document structure including headings, paragraphs, lists
- **Table Extraction**: Tables converted to markdown format with proper formatting
- **Metadata Extraction**: Captures author, creation date, modification date, properties
- **Smart Chunking**: Uses semantic section-based chunking for optimal retrieval

### PowerPoint Presentations (.pptx, .ppt)
- **Slide-by-Slide Extraction**: Each slide becomes a searchable chunk
- **Speaker Notes**: Captures and indexes presenter notes
- **Title and Content**: Preserves slide structure and bullet points
- **Metadata**: Includes slide count and presentation properties

## URL Processing
- **Direct URL Processing**: Fetch and process documents from HTTP/HTTPS
- **Automatic Content Extraction**: Converts HTML to markdown
- **Metadata Preservation**: Captures source URL and fetch timestamp
- **URL Batch Processing**: Process multiple URLs from markdown/JSON files

## Directory Scanning (Enhanced)
- **Recursive Scanning**: Deep directory traversal with `--recursive`
- **Pattern Filtering**: Include/exclude patterns for precise file selection
  - `--include-pattern "*.pdf"` - Only PDFs
  - `--exclude-pattern "**/test/**"` - Skip test directories
- **Dry Run**: Preview files with `--dry-run` before processing
- **Multi-pattern Support**: Multiple include/exclude patterns

## Page-Range Selection (NEW)
- **Specific Pages**: Process only selected pages from PDFs
- **Range Formats**: "1-5", "1,3,5", "1-3,10-15", "10-" (to end)
- **Cost Optimization**: Avoid processing irrelevant pages
- **Progressive Testing**: Test small ranges before full processing

## Enhanced Document Types
- **PDFs**: Technical datasheets with automatic/manual classification
- **Markdown**: Native support with structure preservation
- **Office**: Word and PowerPoint with specialized parsers
- **Web**: Direct URL processing with content extraction

## Usage Examples
```bash
# Office documents
python cli_main.py add report.docx --processing-options keywords
python cli_main.py add presentation.pptx --document-type auto

# Directory scanning
python cli_main.py add data/docs --recursive --include-pattern "*.pdf"
python cli_main.py add data/docs --exclude-pattern "**/test/**" --dry-run

# Page ranges
python cli_main.py add document.pdf --pages "1-10"
python cli_main.py add catalog.pdf --pages "1,5,10-20"

# URL processing
python cli_main.py add https://example.com/datasheet.pdf
python cli_main.py add dummy --url-file batch.json --workers 3
```

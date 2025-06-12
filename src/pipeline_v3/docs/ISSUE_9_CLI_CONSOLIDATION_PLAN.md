# Issue #9: CLI Consolidation Plan

## Overview

**Issue**: Pipeline v3 has two CLI interfaces (`cli_main.py` and `cli_v3.py`) with different capabilities, creating confusion and missing critical features in the production CLI.

**Branch**: `feature/issue-9-cli-consolidation`  
**Status**: Planning Phase  
**Complexity**: High - Major refactoring of core pipeline  
**Risk**: High - Touches core document processing logic  

## Problem Statement

### Current State
1. **Two CLI Interfaces**:
   - `cli_main.py`: Production CLI with advanced features (queue, status, config) but missing batch processing
   - `cli_v3.py`: Legacy CLI with batch/directory processing but admits it's "temporary"

2. **Two Pipeline Implementations**:
   - `EnhancedPipeline`: Used by cli_main.py, missing critical features
   - `ingest_sources()`: Used by cli_v3.py, complete but lacks registry integration

3. **User Confusion**: Documentation promises features that don't work in production CLI

### Gap Analysis

| Feature | cli_v3.py / ingest_sources | cli_main.py / EnhancedPipeline | User Manual Promise |
|---------|---------------------------|--------------------------------|---------------------|
| **Batch Processing** | ✅ Full directory/glob support | ❌ Individual files only | ✅ "Add multiple files" |
| **Document Modes** | ✅ datasheet/generic/auto | ❌ No mode selection | ❌ Not documented |
| **URL Support** | ✅ HTTP/HTTPS fetching | ❌ Local files only | ❌ Not documented |
| **Custom Prompts** | ✅ --prompt parameter | ❌ Not supported | ❌ Not documented |
| **Cache Management** | ✅ Full LZ4 cache system | ❓ Unknown | ✅ Implied |
| **Progress Tracking** | ✅ Detailed stages | ⚠️ Basic only | ✅ Expected |
| **Processing Reports** | ✅ JSON metrics | ❌ Not generated | ✅ Mentioned |
| **Concurrent Batch** | ✅ Configurable | ❌ No batch support | ✅ In config |
| **Document Registry** | ❌ Not integrated | ✅ Full lifecycle | ✅ Required |
| **Queue Management** | ❌ Not supported | ✅ Enterprise features | ✅ Documented |

## Solution Approach

### Strategy: Enhance `EnhancedPipeline` with Missing Features

Port critical functionality from `ingest_sources()` while preserving registry integration and queue management.

### Core Requirements
Every document, whether processed individually or in batch, must:
1. Be tracked in DocumentRegistry for lifecycle management
2. Create storage artifacts (JSONL files)
3. Support all document types (datasheet/generic/markdown)
4. Use cache to avoid redundant API calls
5. Generate both vector and keyword indexes
6. Provide detailed progress tracking
7. Support updates and removal

## Implementation Plan

### Phase 1: Core Pipeline Enhancement
**Goal**: Add missing features to EnhancedPipeline

1. **Document Classification** (`EnhancedPipeline.process_document()`)
   - Add `mode` parameter (datasheet/generic/auto)
   - Integrate `DocumentClassifier.classify()` from parsers.py
   - Route to appropriate parsing strategy

2. **Cache Integration**
   - Verify CacheManager usage in parse operations
   - Ensure cache keys use content + prompt hash
   - Respect cache TTL and compression settings

3. **URL Support**
   - Port `fetch_document()` URL handling logic
   - Support HTTP/HTTPS sources
   - Maintain local file compatibility

4. **Custom Prompt Support**
   - Add prompt_file parameter to process_document()
   - Implement `_resolve_prompt()` logic
   - Allow per-document or global prompts

5. **Progress Monitoring Enhancement**
   - Integrate ProgressMonitor for stage tracking
   - Add stages: classify, fetch, parse, chunk, index_vector, index_keyword
   - Generate processing_report.json

### Phase 2: CLI Enhancement
**Goal**: Update cli_main.py to support all v2.1 features

1. **Enhance `add` Command**
   ```python
   # Current
   python cli_main.py add document.pdf
   
   # Enhanced
   python cli_main.py add document.pdf --mode datasheet --prompt custom.md
   python cli_main.py add "data/*.pdf" --mode auto  # Glob support
   python cli_main.py add data/docs/ --mode generic  # Directory support
   ```

2. **Add `batch` Command** (Optional - if add can't handle all cases)
   ```python
   python cli_main.py batch "**/*.pdf" --mode datasheet --workers 5
   ```

3. **Source Resolution**
   - Implement `_resolve_sources()` to handle:
     - Individual files
     - Directories (recursive)
     - Glob patterns
     - URLs

4. **Concurrent Processing**
   - Respect `pipeline.max_concurrent` from config
   - Use asyncio for parallel document processing
   - Different from queue workers (document-level vs job-level)

### Phase 3: Testing & Validation
**Goal**: Ensure no regression and all features work

1. **Test Matrix**:
   - Individual file processing (existing functionality)
   - Directory batch processing
   - Glob pattern processing
   - URL document fetching
   - Each document mode (datasheet/generic/markdown)
   - Custom prompt usage
   - Cache hit/miss scenarios
   - Progress tracking accuracy
   - Update/remove operations on batch-added docs

2. **Performance Tests**:
   - Batch processing with max_concurrent settings
   - Cache efficiency with repeated documents
   - Memory usage with large batches

### Phase 4: Cleanup & Documentation
**Goal**: Single, clear CLI interface

1. **Deprecate cli_v3.py**
   - Add deprecation warning
   - Update all documentation references
   - Provide migration guide

2. **Update Documentation**
   - Revise USER_MANUAL.md with new features
   - Update QUICK_REFERENCE.md
   - Add examples for all new capabilities
   - Update CLAUDE.md files

3. **Code Cleanup**
   - Remove duplicate code
   - Ensure consistent error handling
   - Add comprehensive docstrings

## Risk Mitigation

### Potential Risks
1. **Breaking existing functionality** - Mitigate with comprehensive testing
2. **Performance regression** - Benchmark before/after
3. **Cache invalidation issues** - Test cache key generation thoroughly
4. **Registry consistency** - Ensure all documents properly tracked

### Rollback Plan
- All work on feature branch
- Can abandon and try alternative approach
- Main branch remains stable

## Success Criteria

1. **Single CLI interface** serving all use cases
2. **Feature parity** with v2.1 (except LlamaParse)
3. **No regression** in existing functionality
4. **All tests passing** including new test cases
5. **Documentation updated** and accurate
6. **Performance maintained** or improved

## Technical Debt Addressed

1. Eliminates confusion from dual CLIs
2. Removes duplicate pipeline implementations
3. Creates single source of truth for document processing
4. Improves maintainability

## Next Steps

1. Review and approve this plan
2. Begin Phase 1 implementation
3. Regular commits with descriptive messages
4. Test incrementally
5. Update status documents as progress is made

## Context Preservation

For future sessions, key information:
- **Branch**: `feature/issue-9-cli-consolidation`
- **Main Goal**: Make cli_main.py support all v2.1 features
- **Key Files**: 
  - `pipeline/enhanced_core.py` (needs features)
  - `core/pipeline.py` (has features to port)
  - `cli/management.py` (needs new commands/options)
- **Test First**: Always verify existing functionality still works

## Commands for Next Session

```bash
# Resume work
cd /Users/seanbergman/Repositories/rag_lab
git checkout feature/issue-9-cli-consolidation

# Check status
git status
git log --oneline -10

# Run existing tests to ensure nothing broken
uv run python -m src.pipeline_v3.cli_main add data/sample_docs/labmax-touch-ds.pdf

# Begin implementation following this plan
```
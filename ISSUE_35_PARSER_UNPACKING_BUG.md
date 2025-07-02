# Issue #35: Parser Unpacking Bug - vision_parse_datasheet returns 2 values but caller expects 3

## Bug Description
When processing datasheet documents, the pipeline fails with:
```
ERROR - Document parsing failed for data/sample_docs/labmax-touch-ds.pdf: too many values to unpack (expected 3)
```

## Root Cause
In `pipeline/enhanced_core.py` line 374, the code expects 3 return values:
```python
markdown, pairs, metadata = await parse_document(
```

But `vision_parse_datasheet` in `core/parsers.py` only returns 2 values:
```python
return md, pairs  # Line 385
```

## Impact
- Cannot process any datasheet documents
- Pipeline fails immediately after successful metadata extraction
- Affects all datasheet mode processing

## Other Functions Affected
Looking at the codebase:
- `vision_parse_datasheet()` returns 2 values: `(md, pairs)`
- `vision_parse_generic()` returns 2 values: `(text, [])`
- `parse_word_document()` returns 3 values: `(markdown, pairs, metadata)`
- `parse_powerpoint_document()` returns 3 values: `(markdown, pairs, metadata)`

## Fix Required
The `vision_parse_datasheet` and `vision_parse_generic` functions need to be updated to return 3 values to match the expected interface:
```python
# Current
return md, pairs

# Should be
return md, pairs, {}  # or appropriate metadata dict
```

## Workaround
Use Word/PowerPoint documents or wait for fix.

## Discovery Context
- Found while testing Issue #27 implementation with fresh data
- Occurred on first document load after database cleanup
- Affects Pipeline v3 core functionality
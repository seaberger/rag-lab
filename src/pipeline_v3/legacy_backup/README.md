# Legacy CLI Backup

This folder contains deprecated CLI interfaces that have been replaced by the consolidated CLI.

## Files:
-  - Original temporary CLI, replaced by 

## Migration:
All functionality has been moved to the main CLI at  with enhanced features:
- Document classification modes  
- Batch processing
- Custom prompts
- URL support
- Concurrent workers

## Usage:
Use the main CLI instead:
```bash
uv run python -m src.pipeline_v3.cli_main --help
```

These files are kept for reference only and will be removed in a future version.

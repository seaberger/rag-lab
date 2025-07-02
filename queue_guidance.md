# Production-Critical Queue Guidance

## 2-Minute Timeout Rule
- **Direct CLI commands timeout after 2 minutes** due to shell limitations
- **PDF processing takes 30-45 seconds per page** with OpenAI Vision API
- **Result**: Direct CLI can only handle ~3-4 pages before timeout

## When to Use Queue System
- ✅ **Always** for production workloads
- ✅ **Always** for documents > 4 pages
- ✅ **Always** for multiple documents
- ✅ **Always** when reliability matters
- ❌ **Never** use direct CLI for large batches

## Queue Architecture Benefits
- **Persistent Job Storage**: SQLite database survives restarts
- **Concurrent Workers**: Configurable parallel processing
- **Automatic Retries**: Handles transient failures gracefully
- **Progress Tracking**: Real-time monitoring of long operations
- **Resource Management**: Prevents system overload

## Production Patterns
1. **Batch Import**: `queue start --workers 8` → submit all docs → monitor
2. **Large Documents**: `queue start --workers 2` for memory-heavy processing
3. **Continuous Processing**: Keep queue running permanently for auto-processing

## Essential Commands
```bash
# Start/manage queue
python cli_main.py queue start --workers 4
python cli_main.py queue status --detailed
python cli_main.py queue stop --wait

# Monitor progress
watch -n 30 'python cli_main.py queue status --detailed'
```

## Key Takeaway
**Default to Queue**: When in doubt, use the queue system for reliability and monitoring.

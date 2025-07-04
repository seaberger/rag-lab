# OpenAI API Hardening Improvements

## Overview

The OpenAI API Hardening initiative (Issues #28 & #29) introduces comprehensive improvements to make the Pipeline v3 system production-ready for enterprise use. These enhancements focus on reliability, error handling, and performance optimization when interacting with OpenAI's APIs.

## Key Improvements

### 1. Centralized API Key Management (Issue #28)

#### Problem Solved
- OpenAI clients were created without explicit API key parameters
- Inconsistent API key handling across the codebase
- Potential authentication failures in production environments

#### Solution
Created a centralized `OpenAIClientFactory` that provides:
- **Consistent API key resolution** with clear priority order
- **Proper error messages** when API keys are missing
- **Type-specific client creation** optimized for different use cases

#### API Key Priority Order
1. **Explicit parameter** (highest priority)
2. **Configuration file** (`config.yaml`)
3. **Environment variable** (`OPENAI_API_KEY`)

#### Usage Example
```python
from utils.openai_client import create_vision_client, create_text_client

# Automatically handles API key resolution
vision_client = create_vision_client(config)
text_client = create_text_client(config)
```

### 2. Enhanced Retry Logic (Issue #29)

#### Problem Solved
- Simple retry logic couldn't handle different error types appropriately
- No exponential backoff leading to API rate limit issues
- Timeout errors on large documents with no intelligent handling
- Thundering herd problem with concurrent retries

#### Solution
Implemented sophisticated `EnhancedRetry` system with:

##### Intelligent Error Classification
- **Retryable errors**: Network issues, server errors, timeouts
- **Non-retryable errors**: Authentication failures, invalid requests
- **Rate-limited errors**: Special handling with extended backoff

##### Retry Strategies
- **Exponential backoff** with configurable base and multiplier
- **Jitter** to prevent thundering herd problems
- **Timeout escalation** for subsequent attempts
- **Circuit breaker pattern** to prevent cascading failures

##### Specialized Configurations

| API Type | Base Delay | Max Delay | Timeout Multiplier | Use Case |
|----------|------------|-----------|-------------------|----------|
| Vision | 2.0s | 120s | 1.5x | PDF parsing with images |
| Text | 1.0s | 60s | 1.3x | Chat completions, keywords |
| Embedding | 0.5s | 30s | 1.2x | Vector embeddings |
| Batch | 3.0s | 180s | 2.0x | Large batch operations |

#### Usage Example
```python
@enhanced_retry_api_call(max_attempts=3, retry_type="vision")
async def call_api():
    return client.chat.completions.create(...)
```

### 3. Large Document Progress Monitoring (Issue #27)

#### Problem Solved
- Silent waits of 20-30 minutes with no feedback
- No visibility into PDF page processing
- Difficult to debug where processing fails

#### Solution
Implemented `PageProgressMonitor` that provides:
- **Real-time page processing updates**
- **Processing time per page**
- **Visual progress indicators**
- **Detailed progress statistics**

#### Progress Output Example
```
📄 Processing page 40 (1/21)...
✅ Page 40 processed in 0.06s
📄 Processing page 41 (2/21)...
✅ Page 41 processed in 0.08s
```

## Configuration

### Timeout Configuration
```yaml
openai:
  timeout_base: 60        # Base timeout for API calls
  timeout_per_page: 30    # Additional timeout per PDF page
  client_timeout: 60      # Client-level timeout
```

### Retry Configuration (Programmatic)
```python
from utils.enhanced_retry import RetryConfig, RetryStrategy

config = RetryConfig(
    max_attempts=3,
    base_delay=1.0,
    max_delay=60.0,
    exponential_base=2.0,
    jitter=True,
    strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
    fail_fast_on_auth=True,
    rate_limit_backoff_multiplier=2.0
)
```

## Error Handling Examples

### Authentication Errors (Fast Failure)
```
❌ OpenAI API key not found. Please set it via:
1. Explicit parameter: create_client(api_key='your-key')
2. Environment variable: OPENAI_API_KEY=your-key
3. Config file with openai.api_key setting
```

### Rate Limit Handling
```
⚠️ Rate limit detected, applying 2.0x backoff multiplier
🔄 Retrying in 4.82s (attempt 2/3)...
```

### Timeout with Escalation
```
⏱️ Attempt 1: timeout escalated to 90.0s
⚠️ Request timed out after 90s, retrying...
⏱️ Attempt 2: timeout escalated to 135.0s
```

## Performance Optimizations

### 1. Connection Reuse
- Centralized client creation reduces connection overhead
- Persistent clients for repeated API calls

### 2. Intelligent Timeouts
- Base timeout + per-page calculation for PDFs
- Timeout escalation prevents premature failures
- Different timeouts for different operation types

### 3. Efficient Retries
- Exponential backoff reduces API load
- Jitter prevents synchronized retry storms
- Fast failure for non-retryable errors saves time

## Monitoring and Debugging

### Client Information
```python
from utils.openai_client import OpenAIClientFactory

info = OpenAIClientFactory.get_api_key_info(config)
# {
#     "api_key_found": True,
#     "source": "environment",
#     "key_prefix": "sk-proj...",
#     "key_length": 56
# }
```

### Retry Metrics
The enhanced retry system logs detailed information:
- Retry attempts and delays
- Error classification results
- Timeout escalation details
- Circuit breaker state changes

## Best Practices

### 1. API Key Management
- Store API keys in environment variables for production
- Use `.env` files for local development
- Never commit API keys to version control

### 2. Retry Configuration
- Use appropriate retry types for different operations
- Adjust timeouts based on document size
- Monitor retry patterns to optimize settings

### 3. Error Handling
- Let non-retryable errors fail fast
- Log retry attempts for debugging
- Use circuit breakers for critical paths

### 4. Large Document Processing
- Use page ranges to test before full processing
- Monitor progress for long operations
- Adjust timeouts based on document complexity

## Migration Guide

### Updating Existing Code

#### Before (Issue #28)
```python
client = OpenAI()  # Implicitly uses environment variable
```

#### After (Issue #28)
```python
from utils.openai_client import create_vision_client
client = create_vision_client(config)  # Explicit, consistent handling
```

#### Before (Issue #29)
```python
@retry_api_call(max_attempts=3)
async def call_api():
    # Simple retry with no backoff
```

#### After (Issue #29)
```python
@enhanced_retry_api_call(max_attempts=3, retry_type="vision")
async def call_api():
    # Sophisticated retry with exponential backoff
```

## Testing the Improvements

### Test API Key Handling
```bash
# Test with missing API key
unset OPENAI_API_KEY
uv run python -m src.pipeline_v3.cli_main add test.pdf
# Should show clear error message

# Test with invalid API key
export OPENAI_API_KEY="invalid-key"
uv run python -m src.pipeline_v3.cli_main add test.pdf
# Should fail fast without retries
```

### Test Retry Logic
```bash
# Process large document to see retry behavior
uv run python -m src.pipeline_v3.cli_main add large.pdf --pages "1-30"
# Watch for retry messages and timeout escalation
```

### Test Progress Monitoring
```bash
# Process with page ranges to see progress
uv run python -m src.pipeline_v3.cli_main add catalog.pdf --pages "1-20"
# See page-by-page progress updates
```

## Troubleshooting

### Common Issues

**Issue**: "API key not found" error
- Check environment variable: `echo $OPENAI_API_KEY`
- Verify `.env` file exists and contains key
- Ensure proper working directory

**Issue**: Repeated timeouts
- **Important**: Distinguish between shell timeout (2 minutes) and API timeout
- For shell timeout: Use `--timeout` parameter (e.g., `--timeout 600` for 10 minutes)
- For API timeout: Reduce page range size or increase `--timeout-per-page` value
- Check document complexity

**Issue**: Rate limit errors
- Reduce concurrent workers
- Increase retry delays in config
- Consider API tier upgrade

### Understanding Timeout Types

#### Shell/Bash Timeout (Default: 2 minutes)
- **What**: The shell terminates any command after 2 minutes
- **When**: Always applies to direct CLI commands
- **Fix**: Use `--timeout` parameter to extend (up to 600 seconds/10 minutes)
- **Example**: `uv run python -m src.pipeline_v3.cli_main add doc.pdf --timeout 600`

#### API Timeout (Configurable)
- **What**: OpenAI API request timeout
- **When**: Applied per API call based on document complexity
- **Fix**: Automatically calculated as `base + (pages × per_page)`
- **Config**: Set in `config.yaml` under `openai.timeout_base` and `openai.timeout_per_page`

## Future Enhancements

Potential improvements being considered:
- Adaptive timeout calculation based on page complexity
- Retry strategy learning from historical data
- Cost tracking and optimization
- Request/response caching for idempotent operations

---

For more information, see:
- [PAGE_RANGE_FEATURE.md](./PAGE_RANGE_FEATURE.md) - Page selection documentation
- [DEVELOPMENT_STATUS.md](../DEVELOPMENT_STATUS.md) - Overall project status
- [Issue #28](https://github.com/seaberger/rag-lab/issues/28) - API Key initialization
- [Issue #29](https://github.com/seaberger/rag-lab/issues/29) - Retry logic improvements

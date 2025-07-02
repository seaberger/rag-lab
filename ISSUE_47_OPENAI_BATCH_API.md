# Issue #47: OpenAI Batch API Integration

## Summary
Implement OpenAI Batch API support for cost-effective bulk document processing. The Batch API offers 50% token cost savings and is ideal for large-scale document processing operations where immediate results are not required.

## Background
Currently, Pipeline v3 processes documents using synchronous OpenAI API calls. For large batches (100+ documents), this approach:
- Incurs full API costs
- Requires maintaining active connections
- Can hit rate limits during peak processing

The OpenAI Batch API addresses these limitations by:
- **50% cost reduction** on all tokens
- **Higher rate limits** for batch operations
- **Asynchronous processing** with no connection overhead
- **Built-in retry logic** for failed requests

## Proposed Solution

### 1. Batch Job Manager
Create a new batch processing system that:
- Collects documents into batch payloads
- Submits batches to OpenAI Batch API
- Monitors batch completion status
- Downloads and processes results
- Integrates with existing queue system

### 2. Implementation Architecture
```
Document Queue → Batch Collector → OpenAI Batch API → Result Processor → Storage
                    ↓                                        ↓
                Max 50k requests                    Poll for completion
                  per batch                           (15-30 minutes)
```

### 3. Key Components

#### BatchCollector
```python
class BatchCollector:
    def __init__(self, max_batch_size=50000, max_wait_time=300):
        self.pending_requests = []
        self.max_batch_size = max_batch_size
        self.max_wait_time = max_wait_time
    
    def add_request(self, doc_id, prompt, images):
        # Add to pending batch
    
    def should_submit(self):
        # Check size or time threshold
    
    def create_batch_payload(self):
        # Format for OpenAI Batch API
```

#### BatchMonitor
```python
class BatchMonitor:
    def __init__(self, openai_client):
        self.client = openai_client
        self.active_batches = {}
    
    async def submit_batch(self, requests):
        # Upload to OpenAI
    
    async def check_status(self, batch_id):
        # Poll for completion
    
    async def download_results(self, batch_id):
        # Retrieve processed data
```

### 4. Integration with Existing Queue

Add new job type for batch processing:
```python
# In DocumentQueue
if self.should_use_batch_api(job_count, job_type):
    batch_job = self.create_batch_job(jobs)
    self.submit_to_batch_processor(batch_job)
else:
    # Existing synchronous processing
```

### 5. Configuration
```yaml
batch_api:
  enabled: true
  max_batch_size: 50000        # Max requests per batch
  min_batch_size: 100          # Min to trigger batch
  max_wait_time: 300           # Max seconds before submission
  check_interval: 60           # Status check frequency
  cost_threshold: 0.50         # Use batch if saves > 50%
```

## Benefits

1. **Cost Savings**: 50% reduction in token costs for bulk operations
2. **Scalability**: Process thousands of documents without rate limits
3. **Reliability**: Built-in retry logic and error handling
4. **Efficiency**: No need to maintain active connections

## Use Cases

1. **Initial Bulk Import**: Processing historical document archives
2. **Scheduled Batch Jobs**: Daily/weekly document processing
3. **Cost-Sensitive Operations**: When processing time is flexible
4. **Large Document Collections**: 100+ documents at once

## Implementation Plan

### Phase 1: Core Batch API Integration
1. Create BatchCollector class
2. Implement BatchMonitor for status tracking
3. Add batch job type to queue system
4. Create result processor

### Phase 2: Intelligent Routing
1. Add decision logic for batch vs sync
2. Implement cost calculation
3. Create batch/sync hybrid mode
4. Add progress tracking

### Phase 3: Production Features
1. Batch failure recovery
2. Partial result handling
3. Monitoring dashboard
4. Cost tracking and reporting

## Success Criteria

1. Successfully process 100+ documents via Batch API
2. Achieve 50% cost reduction vs synchronous API
3. Maintain existing search quality and accuracy
4. Provide clear progress feedback during batch processing

## Risks and Mitigation

1. **Risk**: Longer processing time (15-30 minutes)
   - **Mitigation**: Clear user expectations, progress tracking

2. **Risk**: Batch failures affect many documents
   - **Mitigation**: Automatic retry, partial result recovery

3. **Risk**: Complex integration with existing queue
   - **Mitigation**: Phased implementation, extensive testing

## References

- [OpenAI Batch API Documentation](https://platform.openai.com/docs/guides/batch)
- User's successful implementation: "I implemented that for a >100 doc process using their vision 4.1 model and it worked quite well. It only took about 15 minutes to process for small batches like that and token cost is greatly reduced."

## Priority
Medium - This is a cost optimization feature that would benefit users processing large document collections.

## Labels
- enhancement
- cost-optimization
- openai-api
- batch-processing
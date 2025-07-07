# Tenant Context Architecture Issues and Solutions

## Current Issues

### 1. **No Direct Tenant Specification in Commands**
Currently, you cannot pass `--tenant-id` to commands like search. This forces users to either:
- Change the config file's `default_tenant_id`
- Use the tenant context command (which has limitations)

### 2. **Static Tenant Context in Database Factory**
When the CLI initializes, it creates a `DatabaseFactory` with the default tenant from config:
```python
self.database_factory = DatabaseFactory(self.config)
```

This means all database operations use the config's default tenant, not any dynamically set context.

### 3. **Session-Based Context Not Used**
While we can set tenant context using PostgreSQL session variables:
```sql
SELECT tenants.set_current_tenant('tenant-id')
```

The application doesn't use this - it always uses the tenant ID from config.

### 4. **Registry Lookup Failures**
When searching across tenants, the registry lookup fails because:
- The IndexManager uses one tenant context (from config)
- The registry uses the same tenant context
- Documents from other tenants can't be found in the registry

## Proposed Solutions

### Solution 1: Add --tenant-id Parameter to All Commands
This is the most user-friendly approach:

```bash
# Search in specific tenant
pipeline search "query" --tenant-id 51b272e9-be33-4b63-9afd-7c1ca9d1b403

# Add document to specific tenant
pipeline add document.pdf --tenant-id 51b272e9-be33-4b63-9afd-7c1ca9d1b403

# Get status for specific tenant
pipeline status --tenant-id 51b272e9-be33-4b63-9afd-7c1ca9d1b403
```

Implementation:
1. Add `--tenant-id` argument to all relevant commands
2. Pass tenant_id to DatabaseFactory initialization
3. Use the passed tenant_id instead of config default

### Solution 2: Fix Session-Based Context
Make the application respect PostgreSQL session context:

1. When `tenant context --set` is used, store the tenant ID in a session file
2. Read this session file when initializing DatabaseFactory
3. Priority order: CLI argument > Session file > Config default

### Solution 3: Multi-Tenant Aware Search
For search operations specifically:

1. Create tenant-specific Qdrant collections (e.g., `datasheets_v3_tenant_51b272e9`)
2. Include tenant_id in all document metadata
3. Use proper tenant filtering in all queries

## Implementation Plan

### Phase 1: Add --tenant-id Parameter (Immediate)
1. Modify CLI argument parser to accept --tenant-id
2. Update DatabaseFactory initialization to accept tenant_id parameter
3. Pass tenant_id through the command chain

### Phase 2: Fix Registry Context (Immediate)
1. Ensure registry uses the same tenant context as search operations
2. Add fallback to fetch document info from any tenant (for admin operations)

### Phase 3: Tenant-Specific Collections (Future)
1. Create separate Qdrant collections per tenant
2. Migrate existing data to tenant-specific collections
3. Update search logic to use tenant-specific collections

## Code Changes Required

### 1. CLI Management (cli/management.py)
```python
# Add to parser
parser.add_argument('--tenant-id', help='Tenant ID for multi-tenant operations')

# Update initialize method
def initialize(self, tenant_id=None):
    # Use tenant_id if provided, otherwise use config default
    effective_tenant_id = tenant_id or self.config.database.postgresql.default_tenant_id
    self.database_factory = DatabaseFactory(self.config, tenant_id=effective_tenant_id)
```

### 2. Search Method
```python
async def search(self, args):
    # Initialize with specific tenant if provided
    if hasattr(args, 'tenant_id') and args.tenant_id:
        self.initialize(tenant_id=args.tenant_id)

    # Continue with search...
```

### 3. Index Manager
Ensure tenant_id is properly filtered in all operations.

## Benefits

1. **User Experience**: Users can easily work with multiple tenants without config changes
2. **Security**: Proper tenant isolation at all levels
3. **Flexibility**: Support for cross-tenant operations when needed (admin)
4. **Consistency**: Same tenant context used throughout the operation

## Migration Path

1. First, implement --tenant-id parameter (backward compatible)
2. Update documentation to show new usage patterns
3. Gradually deprecate config-based tenant switching
4. Move to tenant-specific collections in future version

# Pipeline v3 Import Issues Report

This report identifies all files in `src/pipeline_v3` that have imports from "utils" without the full `src.pipeline_v3` prefix. These files would fail to import correctly when the CLI starts up.

## Files with Incorrect Imports

### Core Module Files (High Priority - Used at CLI Startup)

1. **src/pipeline_v3/core/fingerprint.py**
   - Line 15: `from utils.common_utils import logger`
   - Line 16: `from utils.config import PipelineConfig`

2. **src/pipeline_v3/core/change_detector.py**
   - Line 18: `from utils.common_utils import logger`
   - Line 19: `from utils.config import PipelineConfig`

3. **src/pipeline_v3/core/tenant_manager.py**
   - Line 15: `from utils.common_utils import logger`
   - Line 16: `from utils.config import PipelineConfig`

4. **src/pipeline_v3/core/postgres_performance.py**
   - Line 22: `from utils.common_utils import logger`
   - Line 23: `from utils.config import PipelineConfig`

5. **src/pipeline_v3/core/tenant_connection_manager.py**
   - Line 24: `from utils.common_utils import logger`
   - Line 25: `from utils.config import PipelineConfig, PostgreSQLSettings`

6. **src/pipeline_v3/core/tenant_pool_monitor.py**
   - Line 22: `from utils.common_utils import logger`
   - Line 23: `from utils.config import PipelineConfig`

7. **src/pipeline_v3/core/enhanced_pipeline_adapter.py**
   - Line 12: `from utils.common_utils import logger`
   - Line 13: `from utils.config import PipelineConfig`

### Storage Module Files

8. **src/pipeline_v3/storage/keyword_index.py**
   - Line 16: `from utils.common_utils import logger`
   - Line 17: `from utils.config import PipelineConfig`

### CLI Module Files

9. **src/pipeline_v3/cli/commands/performance.py**
   - Line 18: `from utils.config import PipelineConfig`

10. **src/pipeline_v3/cli/commands/migrate.py**
    - Line 24: `from utils.config import PipelineConfig`

11. **src/pipeline_v3/cli/utils/validation.py**
    - Line 10: `from utils.security import PathSecurityValidator, SecurityError`

### Search Module Files

12. **src/pipeline_v3/search/cli.py**
    - Line 18: `from utils.config import PipelineConfig`

### Tools and Scripts

13. **src/pipeline_v3/tools/sqlite_to_postgres.py**
    - Line 21: `from utils.common_utils import logger`
    - Line 22: `from utils.config import PostgreSQLSettings`

14. **src/pipeline_v3/scripts/migrate_to_server.py**
    - Line 20: `from utils.common_utils import logger`

15. **src/pipeline_v3/examples/atomic_operations_demo.py**
    - Line 19: `from utils.config import PipelineConfig`

## Summary

Total files with incorrect imports: **15 files**

These files have direct imports from `utils` package without the full module path. This would cause ImportError when the CLI starts up because Python won't be able to find the `utils` module in the import path.

### Recommended Fix

All imports should be changed from:
```python
from utils.common_utils import logger
from utils.config import PipelineConfig
```

To:
```python
from src.pipeline_v3.utils.common_utils import logger
from src.pipeline_v3.utils.config import PipelineConfig
```

## Additional Notes

- The test files also have similar import issues (47 total files found), but they are lower priority since they don't affect CLI startup
- Some files use relative imports with sys.path manipulation, which is also problematic
- The search/cli.py file has additional issues with relative imports from `search.hybrid` and `storage.keyword_index`

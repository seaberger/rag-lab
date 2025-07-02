# Search Capabilities

## Three Search Types
1. **Vector Search (Semantic)**: Uses OpenAI embeddings for conceptual similarity
2. **Keyword Search (Exact)**: SQLite FTS5 with BM25 ranking for precise terms
3. **Hybrid Search (Recommended)**: Combines both with advanced fusion algorithms

## Enhanced Search Capabilities

### Hybrid Fusion Methods

#### Reciprocal Rank Fusion (RRF)
```bash
# Default fusion method - most reliable
python cli_main.py search "thermopile sensor calibration" --fusion-method rrf
python cli_main.py search "PM10K specifications" --fusion-method rrf --limit 10
```

#### Adaptive Fusion
```bash
# Smart auto-adjusting weights based on query type
python cli_main.py search "PM10K" --fusion-method adaptive  # Favors keyword (model numbers)
python cli_main.py search "thermal measurement principles" --fusion-method adaptive  # Favors vector
python cli_main.py search "PM10K calibration procedure" --fusion-method adaptive  # Balanced approach
```

#### Weighted Fusion
```bash
# Advanced score-based combination with consensus boosting
python cli_main.py search "laser measurement accuracy" --fusion-method weighted
python cli_main.py search "sensor calibration" --fusion-method weighted --vector-weight 0.7
```

### Basic Filtering
```bash
# Filter by specific document IDs
python cli_main.py search "calibration" --filter '{"doc_ids": ["abc123", "def456"]}'

# Basic document filtering
python cli_main.py search "PM10K" --filter '{"doc_ids": ["manual_001"]}' --limit 5
```

### Performance Tips & Examples
```bash
# Model numbers - use keyword or adaptive
python cli_main.py search "PM10K" --search-type keyword  # Fast, exact match
python cli_main.py search "PM10K" --fusion-method adaptive  # Smart weighting

# Technical concepts - use vector or adaptive
python cli_main.py search "thermal conductivity measurement" --search-type vector
python cli_main.py search "sensor calibration theory" --fusion-method adaptive

# General queries - use hybrid with RRF
python cli_main.py search "how to calibrate sensors" --fusion-method rrf

# Include context for better results
python cli_main.py search "PM10K calibration procedure step-by-step" --fusion-method adaptive
```

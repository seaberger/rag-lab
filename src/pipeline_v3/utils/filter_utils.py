"""
Enhanced filtering utilities for Pipeline v3 search functionality.

Provides unified filtering interface for vector, keyword, and hybrid search
with support for metadata, content, date ranges, and more.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from fnmatch import fnmatch

try:
    from utils.common_utils import logger
except ImportError:
    # Handle when called from different contexts
    import logging
    logger = logging.getLogger(__name__)


class FilterBuilder:
    """Builds SQL WHERE clauses and LlamaIndex filters from unified filter dict."""
    
    @staticmethod
    def parse_unified_filters(filters: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Parse and validate unified filter format."""
        if not filters:
            return {}
            
        if not isinstance(filters, dict):
            raise ValueError("Filters must be a dictionary")
            
        # Validate structure
        valid_sections = {
            'doc_ids', 'source', 'metadata', 'pairs', 'content', 'dates', 'processing'
        }
        
        invalid_keys = set(filters.keys()) - valid_sections
        if invalid_keys:
            logger.warning(f"Unknown filter keys ignored: {invalid_keys}")
            
        return {k: v for k, v in filters.items() if k in valid_sections}
    
    @staticmethod
    def build_keyword_sql_filters(filters: Dict[str, Any]) -> Tuple[str, List[Any]]:
        """Build SQL WHERE clause and parameters for keyword search."""
        if not filters:
            return "", []
            
        where_clauses = []
        params = []
        
        # Doc IDs filter (existing functionality)
        if 'doc_ids' in filters and filters['doc_ids']:
            doc_ids = filters['doc_ids']
            placeholders = ",".join("?" * len(doc_ids))
            where_clauses.append(f"keyword_index.doc_id IN ({placeholders})")
            params.extend(doc_ids)
        
        # Source filters
        if 'source' in filters:
            source_filters = filters['source']
            if isinstance(source_filters, dict):
                if 'contains' in source_filters:
                    where_clauses.append("dm.source LIKE ?")
                    params.append(f"%{source_filters['contains']}%")
                if 'not_contains' in source_filters:
                    where_clauses.append("dm.source NOT LIKE ?")
                    params.append(f"%{source_filters['not_contains']}%")
                if 'pattern' in source_filters:
                    # Handle glob patterns via LIKE (basic support)
                    pattern = source_filters['pattern'].replace('*', '%').replace('?', '_')
                    where_clauses.append("dm.source LIKE ?")
                    params.append(pattern)
        
        # Metadata filters
        if 'metadata' in filters:
            meta_filters = filters['metadata']
            if isinstance(meta_filters, dict):
                # Source type filter
                if 'source_type' in meta_filters:
                    where_clauses.append("JSON_EXTRACT(dr.metadata, '$.source_type') = ?")
                    params.append(meta_filters['source_type'])
                    
                # Parse method filter
                if 'parse_method' in meta_filters:
                    where_clauses.append("JSON_EXTRACT(dr.metadata, '$.parse_method') = ?")
                    params.append(meta_filters['parse_method'])
                    
                # File size filters
                if 'file_size' in meta_filters:
                    size_filter = meta_filters['file_size']
                    if isinstance(size_filter, dict):
                        if 'min' in size_filter:
                            where_clauses.append("dr.size >= ?")
                            params.append(size_filter['min'])
                        if 'max' in size_filter:
                            where_clauses.append("dr.size <= ?")
                            params.append(size_filter['max'])
        
        # Pairs filters (model/part numbers)
        if 'pairs' in filters:
            pairs_filters = filters['pairs']
            if isinstance(pairs_filters, dict):
                if 'contains' in pairs_filters:
                    where_clauses.append("dm.pairs LIKE ?")
                    params.append(f"%{pairs_filters['contains']}%")
                if 'model_contains' in pairs_filters:
                    where_clauses.append("dm.pairs LIKE ?")
                    params.append(f"%{pairs_filters['model_contains']}%")
                if 'part_contains' in pairs_filters:
                    where_clauses.append("dm.pairs LIKE ?")
                    params.append(f"%{pairs_filters['part_contains']}%")
        
        # Content filters
        if 'content' in filters:
            content_filters = filters['content']
            if isinstance(content_filters, dict):
                if 'keywords_contain' in content_filters:
                    where_clauses.append("keyword_index.keywords LIKE ?")
                    params.append(f"%{content_filters['keywords_contain']}%")
                if 'text_contains' in content_filters:
                    where_clauses.append("keyword_index.text LIKE ?")
                    params.append(f"%{content_filters['text_contains']}%")
        
        # Date filters
        if 'dates' in filters:
            date_filters = filters['dates']
            if isinstance(date_filters, dict):
                if 'created_after' in date_filters:
                    where_clauses.append("dr.created_at >= ?")
                    params.append(date_filters['created_after'])
                if 'created_before' in date_filters:
                    where_clauses.append("dr.created_at <= ?")
                    params.append(date_filters['created_before'])
                if 'modified_after' in date_filters:
                    where_clauses.append("dr.modified_time >= ?")
                    params.append(date_filters['modified_after'])
        
        # Processing status filters
        if 'processing' in filters:
            proc_filters = filters['processing']
            if isinstance(proc_filters, dict):
                if 'indexed' in proc_filters:
                    if proc_filters['indexed']:
                        where_clauses.append("dr.keyword_indexed = 1 AND dr.vector_indexed = 1")
                    else:
                        where_clauses.append("(dr.keyword_indexed = 0 OR dr.vector_indexed = 0)")
                if 'chunk_count' in proc_filters:
                    chunk_filter = proc_filters['chunk_count']
                    if isinstance(chunk_filter, dict):
                        if 'min' in chunk_filter:
                            where_clauses.append("dr.chunk_count >= ?")
                            params.append(chunk_filter['min'])
                        if 'max' in chunk_filter:
                            where_clauses.append("dr.chunk_count <= ?")
                            params.append(chunk_filter['max'])
                if 'has_keywords' in proc_filters:
                    if proc_filters['has_keywords']:
                        where_clauses.append("keyword_index.keywords IS NOT NULL AND keyword_index.keywords != ''")
                    else:
                        where_clauses.append("(keyword_index.keywords IS NULL OR keyword_index.keywords = '')")
        
        # Combine all where clauses
        if where_clauses:
            return " AND " + " AND ".join(where_clauses), params
        else:
            return "", []
    
    @staticmethod
    def build_vector_metadata_filters(filters: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Build LlamaIndex metadata filters for vector search."""
        if not filters:
            return None
            
        # LlamaIndex uses nested dict format for metadata filters
        metadata_filters = {}
        
        # Doc IDs filter - convert to metadata filter
        if 'doc_ids' in filters and filters['doc_ids']:
            metadata_filters['doc_id'] = {'$in': filters['doc_ids']}
        
        # Source filters - LlamaIndex can filter on source metadata
        if 'source' in filters:
            source_filters = filters['source']
            if isinstance(source_filters, dict):
                if 'contains' in source_filters:
                    metadata_filters['source'] = {'$contains': source_filters['contains']}
                # Note: LlamaIndex has limited pattern matching compared to SQL
        
        # Metadata filters
        if 'metadata' in filters:
            meta_filters = filters['metadata']
            if isinstance(meta_filters, dict):
                if 'source_type' in meta_filters:
                    metadata_filters['source_type'] = meta_filters['source_type']
                if 'parse_method' in meta_filters:
                    metadata_filters['parse_method'] = meta_filters['parse_method']
                # File size filters would need custom implementation in LlamaIndex
        
        # Pairs filters - can filter on pairs metadata
        if 'pairs' in filters:
            pairs_filters = filters['pairs']
            if isinstance(pairs_filters, dict):
                # This would require custom logic since pairs are stored as list
                # For now, we'll handle this in post-processing
                pass
        
        # Content filters - text filtering happens at query level
        # Date filters - would need custom metadata field handling
        # Processing filters - handled by index existence
        
        return metadata_filters if metadata_filters else None
    
    @staticmethod  
    def apply_post_vector_filters(results: List[Dict[str, Any]], filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Apply filters that can't be handled by LlamaIndex metadata filters."""
        if not filters or not results:
            return results
            
        filtered_results = []
        
        for result in results:
            include = True
            metadata = result.get('metadata', {})
            
            # Pairs filters
            if 'pairs' in filters and include:
                pairs_filters = filters['pairs']
                if isinstance(pairs_filters, dict):
                    pairs = metadata.get('pairs', [])
                    pairs_str = json.dumps(pairs) if pairs else ""
                    
                    if 'contains' in pairs_filters:
                        if pairs_filters['contains'] not in pairs_str:
                            include = False
                    if 'model_contains' in pairs_filters and include:
                        # Check if any model field contains the text
                        model_match = any(
                            pairs_filters['model_contains'] in str(pair[0]) 
                            for pair in pairs if isinstance(pair, (list, tuple)) and len(pair) >= 1
                        )
                        if not model_match:
                            include = False
                    if 'part_contains' in pairs_filters and include:
                        # Check if any part field contains the text
                        part_match = any(
                            pairs_filters['part_contains'] in str(pair[1]) 
                            for pair in pairs if isinstance(pair, (list, tuple)) and len(pair) >= 2
                        )
                        if not part_match:
                            include = False
            
            # File size filters (if available in metadata)
            if 'metadata' in filters and include:
                meta_filters = filters['metadata']
                if isinstance(meta_filters, dict) and 'file_size' in meta_filters:
                    size_filter = meta_filters['file_size']
                    file_size = metadata.get('file_size')
                    if file_size and isinstance(size_filter, dict):
                        if 'min' in size_filter and file_size < size_filter['min']:
                            include = False
                        if 'max' in size_filter and file_size > size_filter['max']:
                            include = False
            
            # Content filters
            if 'content' in filters and include:
                content_filters = filters['content']
                if isinstance(content_filters, dict):
                    content = result.get('content', '')
                    if 'text_contains' in content_filters:
                        if content_filters['text_contains'] not in content:
                            include = False
                    # Keywords would need to be in metadata or content
                    if 'keywords_contain' in content_filters and include:
                        keywords = metadata.get('keywords', [])
                        if isinstance(keywords, list):
                            keywords_str = ' '.join(keywords)
                        else:
                            keywords_str = str(keywords)
                        if content_filters['keywords_contain'] not in keywords_str:
                            include = False
            
            if include:
                filtered_results.append(result)
                
        return filtered_results


def validate_filter_format(filter_dict: Dict[str, Any]) -> bool:
    """Validate that filter dictionary follows expected format."""
    try:
        FilterBuilder.parse_unified_filters(filter_dict)
        return True
    except Exception as e:
        logger.error(f"Invalid filter format: {e}")
        return False
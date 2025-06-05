"""
Output formatting utilities for CLI.
"""

import json
from typing import Any, Dict, List, Optional
from datetime import datetime


class OutputFormatter:
    """Handles formatting of CLI output in various formats."""
    
    @staticmethod
    def format_json(data: Any, indent: int = 2) -> str:
        """Format data as JSON."""
        return json.dumps(data, indent=indent, default=str)
    
    @staticmethod
    def format_table(data: List[Dict[str, Any]], headers: Optional[List[str]] = None) -> str:
        """Format data as a simple table."""
        if not data:
            return "No data to display"
        
        if headers is None:
            headers = list(data[0].keys()) if data else []
        
        # Calculate column widths
        col_widths = {header: len(header) for header in headers}
        for row in data:
            for header in headers:
                value = str(row.get(header, ''))
                col_widths[header] = max(col_widths[header], len(value))
        
        # Format header
        header_line = " | ".join(header.ljust(col_widths[header]) for header in headers)
        separator = "-" * len(header_line)
        
        # Format rows
        rows = []
        for row in data:
            row_line = " | ".join(
                str(row.get(header, '')).ljust(col_widths[header]) 
                for header in headers
            )
            rows.append(row_line)
        
        return "\n".join([header_line, separator] + rows)
    
    @staticmethod
    def format_status(status_data: Dict[str, Any]) -> str:
        """Format system status information."""
        lines = []
        
        def format_section(name: str, data: Dict[str, Any], indent: int = 0):
            prefix = "  " * indent
            lines.append(f"{prefix}{name}:")
            
            for key, value in data.items():
                if isinstance(value, dict):
                    format_section(key, value, indent + 1)
                else:
                    lines.append(f"{prefix}  {key}: {value}")
        
        format_section("System Status", status_data)
        return "\n".join(lines)
    
    @staticmethod
    def format_search_results(results: List[Dict[str, Any]], detailed: bool = False) -> str:
        """Format search results for display."""
        if not results:
            return "No results found"
        
        lines = [f"Found {len(results)} results:\n"]
        
        for i, result in enumerate(results, 1):
            score = result.get('score', 0)
            source = result.get('source', 'unknown')
            
            lines.append(f"{i}. {source} (score: {score:.3f})")
            
            if detailed:
                content = result.get('content', '')
                if content:
                    # Truncate content for display
                    content_preview = content[:200] + "..." if len(content) > 200 else content
                    lines.append(f"   Content: {content_preview}")
                
                metadata = result.get('metadata', {})
                if metadata:
                    lines.append(f"   Metadata: {metadata}")
            else:
                content = result.get('content', '')
                if content:
                    content_preview = content[:100] + "..." if len(content) > 100 else content
                    lines.append(f"   {content_preview}")
            
            lines.append("")  # Empty line between results
        
        return "\n".join(lines)
    
    @staticmethod
    def format_progress_bar(current: int, total: int, width: int = 50) -> str:
        """Format a simple progress bar."""
        if total == 0:
            return "[" + "=" * width + "] 100%"
        
        progress = current / total
        filled = int(width * progress)
        bar = "=" * filled + "-" * (width - filled)
        percentage = int(progress * 100)
        
        return f"[{bar}] {percentage}% ({current}/{total})"
    
    @staticmethod
    def format_duration(seconds: float) -> str:
        """Format duration in human readable format."""
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.1f}m"
        else:
            hours = seconds / 3600
            return f"{hours:.1f}h"
    
    @staticmethod
    def format_timestamp(timestamp: datetime) -> str:
        """Format timestamp for display."""
        return timestamp.strftime("%Y-%m-%d %H:%M:%S")
    
    @staticmethod
    def format_file_size(size_bytes: int) -> str:
        """Format file size in human readable format."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f}{unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f}TB"
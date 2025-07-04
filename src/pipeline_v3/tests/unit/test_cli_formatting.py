"""
Unit tests for CLI formatting utilities.
"""

import json
from datetime import datetime

import pytest

from ...cli.utils.formatting import OutputFormatter


class TestOutputFormatter:
    """Test the OutputFormatter class methods."""

    def test_format_json_basic(self):
        """Test basic JSON formatting."""
        data = {"key": "value", "number": 42}
        result = OutputFormatter.format_json(data)

        # Should be valid JSON
        parsed = json.loads(result)
        assert parsed == data

        # Should be indented (default 2 spaces)
        assert "  " in result

    def test_format_json_custom_indent(self):
        """Test JSON formatting with custom indent."""
        data = {"nested": {"key": "value"}}
        result = OutputFormatter.format_json(data, indent=4)

        # Should use 4-space indentation
        lines = result.split('\n')
        assert any(line.startswith('    ') for line in lines)

    def test_format_json_with_datetime(self):
        """Test JSON formatting with datetime objects."""
        dt = datetime(2023, 1, 1, 12, 0, 0)
        data = {"timestamp": dt, "value": 42}
        result = OutputFormatter.format_json(data)

        # Should handle datetime serialization
        parsed = json.loads(result)
        assert "2023-01-01" in parsed["timestamp"]

    def test_format_table_empty(self):
        """Test table formatting with empty data."""
        result = OutputFormatter.format_table([])
        assert result == "No data to display"

    def test_format_table_basic(self):
        """Test basic table formatting."""
        data = [
            {"name": "John", "age": 30, "city": "NYC"},
            {"name": "Jane", "age": 25, "city": "LA"}
        ]
        result = OutputFormatter.format_table(data)

        lines = result.split('\n')
        assert len(lines) == 4  # header, separator, 2 data rows
        assert "name" in lines[0]
        assert "age" in lines[0]
        assert "city" in lines[0]
        assert "John" in lines[2]
        assert "Jane" in lines[3]

    def test_format_table_custom_headers(self):
        """Test table formatting with custom headers."""
        data = [{"a": 1, "b": 2, "c": 3}]
        headers = ["a", "c"]  # Skip column "b"
        result = OutputFormatter.format_table(data, headers)

        assert "a" in result
        assert "c" in result
        assert "b" not in result

    def test_format_table_missing_values(self):
        """Test table formatting with missing values."""
        data = [
            {"name": "John", "age": 30},
            {"name": "Jane", "city": "LA"}  # Missing age
        ]
        result = OutputFormatter.format_table(data)

        # Should handle missing values gracefully
        lines = result.split('\n')
        assert len(lines) == 4
        assert "Jane" in lines[3]

    def test_format_table_column_width_calculation(self):
        """Test table formatting handles varying column widths."""
        data = [
            {"short": "a", "very_long_column_name": "b"},
            {"short": "very long value here", "very_long_column_name": "c"}
        ]
        result = OutputFormatter.format_table(data)

        # Should align columns properly
        lines = result.split('\n')
        header_line = lines[0]
        data_line = lines[2]

        # Column positions should align
        short_pos = header_line.find("short")
        long_pos = header_line.find("very_long_column_name")
        assert short_pos < long_pos

    def test_format_status_simple(self):
        """Test status formatting with simple data."""
        status_data = {
            "version": "1.0.0",
            "status": "running",
            "uptime": "24h"
        }
        result = OutputFormatter.format_status(status_data)

        assert "System Status:" in result
        assert "version: 1.0.0" in result
        assert "status: running" in result

    def test_format_status_nested(self):
        """Test status formatting with nested data."""
        status_data = {
            "database": {
                "status": "connected",
                "connections": 5
            },
            "api": {
                "status": "healthy",
                "requests": 1000
            }
        }
        result = OutputFormatter.format_status(status_data)

        lines = result.split('\n')

        # Should have nested structure
        assert "database:" in result
        assert "  status: connected" in result
        assert "api:" in result
        assert "  status: healthy" in result

    def test_format_search_results_empty(self):
        """Test search results formatting with no results."""
        result = OutputFormatter.format_search_results([])
        assert result == "No results found"

    def test_format_search_results_basic(self):
        """Test basic search results formatting."""
        results = [
            {
                "score": 0.95,
                "source": "document1.pdf",
                "content": "This is some content"
            },
            {
                "score": 0.87,
                "source": "document2.pdf",
                "content": "This is other content"
            }
        ]
        result = OutputFormatter.format_search_results(results)

        assert "Found 2 results:" in result
        assert "1. document1.pdf (score: 0.950)" in result
        assert "2. document2.pdf (score: 0.870)" in result
        assert "This is some content" in result

    def test_format_search_results_detailed(self):
        """Test detailed search results formatting."""
        results = [
            {
                "score": 0.95,
                "source": "document1.pdf",
                "content": "This is some content",
                "metadata": {"page": 1, "section": "intro"}
            }
        ]
        result = OutputFormatter.format_search_results(results, detailed=True)

        assert "Metadata: {'page': 1, 'section': 'intro'}" in result
        assert "This is some content" in result

    def test_format_search_results_content_truncation(self):
        """Test search results content truncation."""
        long_content = "a" * 300
        results = [
            {
                "score": 0.95,
                "source": "document.pdf",
                "content": long_content
            }
        ]

        # Test non-detailed (100 char limit)
        result = OutputFormatter.format_search_results(results, detailed=False)
        content_line = [line for line in result.split('\n') if line.strip().startswith('a')]
        assert len(content_line[0].strip()) <= 104  # 100 + "..."

        # Test detailed (200 char limit)
        result_detailed = OutputFormatter.format_search_results(results, detailed=True)
        content_lines = [line for line in result_detailed.split('\n') if "Content:" in line]
        assert len(content_lines[0]) <= 220  # Allow for "Content: " prefix

    def test_format_progress_bar_empty(self):
        """Test progress bar with zero total."""
        result = OutputFormatter.format_progress_bar(0, 0)
        assert "[" + "=" * 50 + "] 100%" in result

    def test_format_progress_bar_partial(self):
        """Test progress bar with partial completion."""
        result = OutputFormatter.format_progress_bar(25, 100)
        assert "25%" in result
        assert "(25/100)" in result

        # Should have some filled and some unfilled sections
        assert "=" in result
        assert "-" in result

    def test_format_progress_bar_complete(self):
        """Test progress bar with complete progress."""
        result = OutputFormatter.format_progress_bar(100, 100)
        assert "100%" in result
        assert "(100/100)" in result
        assert "=" * 50 in result

    def test_format_progress_bar_custom_width(self):
        """Test progress bar with custom width."""
        result = OutputFormatter.format_progress_bar(50, 100, width=20)

        # Should use custom width
        bar_section = result[result.find('[') + 1:result.find(']')]
        assert len(bar_section) == 20

    def test_format_duration_seconds(self):
        """Test duration formatting for seconds."""
        assert OutputFormatter.format_duration(30.5) == "30.5s"
        assert OutputFormatter.format_duration(59.9) == "59.9s"

    def test_format_duration_minutes(self):
        """Test duration formatting for minutes."""
        assert OutputFormatter.format_duration(60) == "1.0m"
        assert OutputFormatter.format_duration(90) == "1.5m"
        assert OutputFormatter.format_duration(3540) == "59.0m"

    def test_format_duration_hours(self):
        """Test duration formatting for hours."""
        assert OutputFormatter.format_duration(3600) == "1.0h"
        assert OutputFormatter.format_duration(7200) == "2.0h"
        assert OutputFormatter.format_duration(5400) == "1.5h"

    def test_format_timestamp(self):
        """Test timestamp formatting."""
        dt = datetime(2023, 12, 25, 15, 30, 45)
        result = OutputFormatter.format_timestamp(dt)
        assert result == "2023-12-25 15:30:45"

    def test_format_file_size_bytes(self):
        """Test file size formatting for bytes."""
        assert OutputFormatter.format_file_size(500) == "500.0B"
        assert OutputFormatter.format_file_size(1023) == "1023.0B"

    def test_format_file_size_kilobytes(self):
        """Test file size formatting for kilobytes."""
        assert OutputFormatter.format_file_size(1024) == "1.0KB"
        assert OutputFormatter.format_file_size(2048) == "2.0KB"
        assert OutputFormatter.format_file_size(1536) == "1.5KB"

    def test_format_file_size_megabytes(self):
        """Test file size formatting for megabytes."""
        assert OutputFormatter.format_file_size(1024 * 1024) == "1.0MB"
        assert OutputFormatter.format_file_size(1024 * 1024 * 2.5) == "2.5MB"

    def test_format_file_size_gigabytes(self):
        """Test file size formatting for gigabytes."""
        assert OutputFormatter.format_file_size(1024 * 1024 * 1024) == "1.0GB"
        assert OutputFormatter.format_file_size(1024 * 1024 * 1024 * 1.5) == "1.5GB"

    def test_format_file_size_terabytes(self):
        """Test file size formatting for terabytes."""
        size = 1024 * 1024 * 1024 * 1024
        assert OutputFormatter.format_file_size(size) == "1.0TB"

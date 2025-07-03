"""
Security tests for SQL injection vulnerabilities in Pipeline v3.

These tests verify that the system properly handles malicious inputs
and uses parameterized queries throughout.
"""

import re
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.registry import DocumentRegistry
from storage.keyword_index import BM25Index as KeywordIndex


class TestSQLInjectionProtection:
    """Test suite for SQL injection protection."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test databases."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def registry(self, temp_dir):
        """Create a test document registry."""
        # DocumentRegistry uses config to determine db path
        # For testing, we'll patch the config
        from utils.config import PipelineConfig

        config = PipelineConfig()
        config.storage.document_registry_path = str(Path(temp_dir) / "test_registry.db")
        return DocumentRegistry(config=config)

    @pytest.fixture
    def keyword_index(self, temp_dir):
        """Create a test keyword index."""
        # KeywordIndex uses config to determine db path
        from utils.config import PipelineConfig

        config = PipelineConfig()
        config.storage.keyword_index_path = str(Path(temp_dir) / "test_keywords.db")
        return KeywordIndex(config=config)

    @pytest.mark.security
    def test_registry_add_document_sql_injection(self, registry):
        """Test that registry.add_document is safe from SQL injection."""
        # Common SQL injection patterns
        malicious_inputs = [
            "'; DROP TABLE documents; --",
            "' OR '1'='1",
            "'; DELETE FROM documents WHERE '1'='1'; --",
            "' UNION SELECT * FROM documents --",
            "1'; UPDATE documents SET status='processed' WHERE '1'='1'; --",
            "Robert'); DROP TABLE documents;--",
            "' OR 1=1--",
            "' OR 'x'='x",
            "\\'; DROP TABLE documents; --",
            "'; EXEC xp_cmdshell('dir'); --",
        ]

        # Test each malicious input
        for malicious_input in malicious_inputs:
            # Should handle malicious file paths safely
            doc_id = registry.register_document(
                source=malicious_input,
                content_hash=f"test_hash_{malicious_input}",
                size=1000,
                modified_time=0,
                metadata={"test": "data"}
            )

            # Should handle malicious metadata safely
            doc_id2 = registry.register_document(
                source=f"test_{malicious_input}.pdf",
                content_hash=f"test_hash2_{malicious_input}",
                size=1000,
                modified_time=0,
                metadata={"key": malicious_input}
            )

            # Verify the database is still intact
            docs = registry.list_documents()
            assert isinstance(docs, list)

            # Verify no tables were dropped
            # Access connection directly for testing
            cursor = registry.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            assert "documents" in tables

    @pytest.mark.security
    def test_keyword_search_sql_injection(self, keyword_index):
        """Test that keyword search is safe from SQL injection."""
        # Add some test documents
        from llama_index.core.schema import TextNode

        test_node = TextNode(
            text="This is a test document with some content.",
            metadata={"type": "test", "title": "Test Document"}
        )
        keyword_index.index_nodes([test_node], doc_id="doc1", source="test.pdf", pairs=[])

        # SQL injection attempts in search queries
        malicious_queries = [
            "'; DROP TABLE documents_fts; --",
            "' OR '1'='1",
            "' UNION SELECT * FROM documents_fts --",
            "test' AND 1=1 UNION SELECT 1,2,3,4 --",
            "'; DELETE FROM documents_fts; --",
            '" OR ""="',
            "' OR ''='",
        ]

        for malicious_query in malicious_queries:
            # Search should handle malicious queries safely
            try:
                results = keyword_index.search(malicious_query, limit=10)
                # Should return results (possibly empty) without errors
                assert isinstance(results, list)
            except Exception as e:
                # If it fails, it should be a legitimate search error,
                # not a SQL injection success
                assert "syntax error" not in str(e).lower()
                assert "drop" not in str(e).lower()
                assert "delete" not in str(e).lower()

            # Verify FTS table still exists and has data
            # Access connection directly for testing
            cursor = keyword_index.conn.execute("SELECT COUNT(*) FROM documents_fts")
            count = cursor.fetchone()[0]
            assert count > 0  # Our test document should still be there


    @pytest.mark.security
    def test_parameterized_queries_used(self):
        """Verify that parameterized queries are used throughout the codebase."""
        # This is more of a code review test - checking for patterns

        # Check key files for dangerous SQL patterns
        files_to_check = [
            "src/pipeline_v3/core/registry.py",
            "src/pipeline_v3/core/keyword_index.py",
            "src/pipeline_v3/storage/sqlite_manager.py",
            "src/pipeline_v3/core/fingerprint.py",
            "src/pipeline_v3/job_queue/storage.py",
        ]

        for file_path in files_to_check:
            if Path(file_path).exists():
                with Path(file_path).open() as f:
                    content = f.read()

                # Find all execute statements
                execute_patterns = re.findall(r"\.execute\((.*?)\)", content, re.DOTALL)

                for pattern in execute_patterns:
                    # Check if it's using placeholders (? or :name)
                    if ("SELECT" in pattern or "INSERT" in pattern or "UPDATE" in pattern) and any(
                        op in pattern for op in [" + ", " % ", ".format("]
                    ):
                        pytest.fail(
                            f"Potential SQL injection vulnerability in {file_path}: "
                            f"Direct string manipulation in SQL query"
                        )

    @pytest.mark.security
    def test_special_characters_handling(self, registry, keyword_index):
        """Test handling of special characters that could be used in attacks."""
        special_chars_inputs = [
            "test'; --",
            "test/*comment*/data",
            "test\\x00null",
            "test\ndata",
            "test\rdata",
            "test\tdata",
            'test"quote',
            "test'quote",
            "test`backtick",
            "test${variable}",
            "test{{template}}",
            "test<script>alert('xss')</script>",
            "test%00null",
            "test%27encoded",
        ]

        for idx, special_input in enumerate(special_chars_inputs):
            # Test document registry
            doc_id = registry.register_document(
                source=f"{special_input}.pdf",
                content_hash=f"test_hash_{idx}",
                size=1000,
                modified_time=idx,
                metadata={"content": special_input},
            )

            # Verify it was stored correctly
            doc = registry.get_document(doc_id)
            assert doc is not None
            assert special_input in doc.source

            # Test keyword index
            from llama_index.core.schema import TextNode

            test_node = TextNode(
                text=f"Content with {special_input}",
                metadata={"test": special_input, "title": special_input}
            )
            keyword_index.index_nodes([test_node], doc_id=f"doc_{special_input}", source=f"{special_input}.pdf", pairs=[])

            # Search for it
            results = keyword_index.search(special_input.replace("'", "''"), limit=10)
            # Should handle the search without SQL errors
            assert isinstance(results, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "security"])

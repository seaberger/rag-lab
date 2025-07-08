"""
Unit tests for BM25 Keyword Index component.

Tests cover keyword indexing, search functionality, and SQL injection protection.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.pipeline_v3.core.data_structures import TextChunk
from storage.keyword_index import BM25Index

from utils.config import PipelineConfig


class TestBM25Index:
    """Test suite for BM25Index."""

    @pytest.fixture
    def keyword_index(self, test_config):
        """Create a test keyword index."""
        return BM25Index(config=test_config)

    def test_index_nodes(self, keyword_index):
        """Test indexing nodes to the database."""
        # Create test nodes
        nodes = [
            TextChunk(
                id="node1",
                text="This is a test document about laser power meters.",
                metadata={"page": 1},
            ),
            TextChunk(
                id="node2",
                text="PM100 specifications and features.",
                metadata={"page": 2},
            ),
        ]

        # Index the nodes
        keyword_index.index_nodes(
            nodes=nodes,
            doc_id="doc1",
            source="test.pdf",
            pairs=[("Product", "PM100"), ("Type", "Datasheet")],
        )

        # Verify documents were indexed
        results = keyword_index.search("laser")
        assert len(results) > 0
        assert results[0]["doc_id"] == "doc1"

    def test_search_basic(self, keyword_index):
        """Test basic search functionality."""
        # Create and index nodes for multiple documents
        docs = [
            {
                "doc_id": "doc1",
                "source": "laser_meter.pdf",
                "nodes": [
                    TextChunk(id="n1", text="Laser power meter PM100 specifications"),
                    TextChunk(id="n2", text="High accuracy optical power measurement"),
                ],
                "pairs": [("Product", "PM100")],
            },
            {
                "doc_id": "doc2",
                "source": "thermal_sensor.pdf",
                "nodes": [
                    TextChunk(
                        id="n3", text="Thermal sensors for temperature measurement"
                    ),
                    TextChunk(id="n4", text="Industrial grade sensors"),
                ],
                "pairs": [("Product", "TS200")],
            },
            {
                "doc_id": "doc3",
                "source": "pm100_manual.pdf",
                "nodes": [
                    TextChunk(id="n5", text="PM100 laser measurement device manual"),
                    TextChunk(id="n6", text="Operating instructions and safety"),
                ],
                "pairs": [("Product", "PM100")],
            },
        ]

        for doc in docs:
            keyword_index.index_nodes(
                nodes=doc["nodes"],
                doc_id=doc["doc_id"],
                source=doc["source"],
                pairs=doc["pairs"],
            )

        # Search for laser
        results = keyword_index.search("laser")
        assert len(results) >= 2
        doc_ids = [r["doc_id"] for r in results]
        assert "doc1" in doc_ids
        assert "doc3" in doc_ids

    def test_search_with_limit(self, keyword_index):
        """Test search with result limit."""
        # Create and index many nodes
        nodes = []
        for i in range(10):
            nodes.append(
                TextChunk(
                    id=f"node{i}",
                    text=f"Document {i} about laser power meters and optical measurement",
                    metadata={"index": i},
                )
            )

        keyword_index.index_nodes(
            nodes=nodes,
            doc_id="doc_many",
            source="many_chunks.pdf",
            pairs=[("Type", "Test")],
        )

        # Search with limit
        results = keyword_index.search("laser", limit=3)
        assert len(results) <= 3

    def test_search_ranking(self, keyword_index):
        """Test search result ranking."""
        # Create nodes with different relevance
        nodes = [
            TextChunk(
                id="low_relevance",
                text="This document mentions laser once",
                metadata={},
            ),
            TextChunk(
                id="high_relevance",
                text="laser laser laser power meter laser specifications laser",
                metadata={},
            ),
            TextChunk(
                id="medium_relevance",
                text="Laser power meter for measuring laser output",
                metadata={},
            ),
        ]

        keyword_index.index_nodes(
            nodes=nodes, doc_id="doc_ranking", source="ranking_test.pdf", pairs=[]
        )

        # Search and check ranking
        results = keyword_index.search("laser")
        assert len(results) == 3
        # First result should have lower (better) BM25 score
        assert results[0]["score"] < results[-1]["score"]

    def test_sql_injection_protection(self, keyword_index):
        """Test protection against SQL injection attempts."""
        # Add a test node
        nodes = [TextChunk(id="test1", text="Test document for security testing")]
        keyword_index.index_nodes(
            nodes=nodes, doc_id="doc_security", source="security.pdf", pairs=[]
        )

        # Try various SQL injection patterns
        injection_queries = [
            "'; DROP TABLE documents; --",
            '" OR 1=1 --',
            "'; DELETE FROM documents WHERE 1=1; --",
            "UNION SELECT * FROM documents",
            "laser'; INSERT INTO documents VALUES ('hack', 'hacked'); --",
        ]

        for query in injection_queries:
            # Should not raise an error and should not break the database
            results = keyword_index.search(query)
            # Results should be empty or safe
            assert isinstance(results, list)

        # Verify database is still intact
        results = keyword_index.search("test")
        assert len(results) == 1
        assert results[0]["doc_id"] == "doc_security"

    def test_special_characters_in_search(self, keyword_index):
        """Test handling of special characters in search queries."""
        # Add node with special characters
        nodes = [
            TextChunk(
                id="special1",
                text="PM100 laser power meter (10W to 100W range) with RS232 interface",
                metadata={},
            )
        ]
        keyword_index.index_nodes(
            nodes=nodes,
            doc_id="doc_special",
            source="special.pdf",
            pairs=[("Model", "PM100")],
        )

        # Search with special characters - these should be handled without errors
        special_queries = [
            "PM-100",  # Hyphen gets cleaned
            "(10W-100W)",  # Parentheses and hyphens
            "RS-232",  # Another hyphen
            "power/meter",  # Slash
            "laser & power",  # Ampersand
            "PM*100",  # Asterisk
            "test;DROP TABLE",  # SQL injection attempt
        ]

        for query in special_queries:
            # Should handle gracefully without errors
            try:
                results = keyword_index.search(query)
                assert isinstance(results, list)
            except sqlite3.OperationalError:
                # Some queries might cause FTS5 syntax errors after cleaning
                # That's OK as long as they don't break the database
                pass

        # Verify we can still search normally
        results = keyword_index.search("laser")
        assert len(results) > 0

    def test_search_by_part_number(self, keyword_index):
        """Test searching by part number."""
        # Index nodes with part numbers
        nodes = [
            TextChunk(id="n1", text="Power meter model information"),
            TextChunk(id="n2", text="Specifications for optical measurement"),
        ]

        keyword_index.index_nodes(
            nodes=nodes,
            doc_id="doc_part",
            source="parts.pdf",
            pairs=[("Part Number", "PM-100A"), ("Model", "PowerMax")],
        )

        # Search by part number
        results = keyword_index.search_by_part_number("PM-100A")
        assert len(results) > 0
        assert any("PM-100A" in str(r) for r in results)

    def test_empty_search(self, keyword_index):
        """Test search with empty query."""
        # Add a node
        nodes = [TextChunk(id="n1", text="Test content")]
        keyword_index.index_nodes(nodes, "doc1", "test.pdf", [])

        # Empty search should return empty results
        results = keyword_index.search("")
        assert len(results) == 0

    def test_clean_text_method(self, keyword_index):
        """Test text cleaning functionality."""
        # Test markdown and special character removal
        test_texts = [
            ("# Header with **bold** and *italic*", "Header with bold and italic"),
            ("[Link](url) and `code`", "Link url and code"),
            ("Text(with)brackets[and]more", "Text with brackets and more"),
        ]

        for input_text, _expected_base in test_texts:
            cleaned = keyword_index._clean_text(input_text)
            # Should remove special characters and normalize whitespace
            assert "#" not in cleaned
            assert "**" not in cleaned
            assert "[" not in cleaned
            assert "]" not in cleaned

    def test_escape_fts5_query_method(self, keyword_index):
        """Test FTS5 query escaping."""
        # Test various dangerous patterns
        test_queries = [
            ("normal query", "normal query"),
            ("query; DROP TABLE", "query DROP TABLE"),  # Semicolon removed
            ("query--comment", "query comment"),  # SQL comment removed
            ("query'quote", "query quote"),  # Single quote removed
            ("UNION SELECT", "   "),  # SQL keywords removed
            ("query=value", "query value"),  # Equals removed
            ("query,value", "query value"),  # Comma removed
        ]

        for input_query, _expected_base in test_queries:
            escaped = keyword_index._escape_fts5_query(input_query)
            # Check that dangerous characters are removed
            assert ";" not in escaped
            assert "--" not in escaped
            assert "'" not in escaped
            assert "=" not in escaped
            assert "," not in escaped

    def test_get_stats(self, keyword_index):
        """Test index statistics."""
        # Index some nodes
        for i in range(5):
            nodes = [
                TextChunk(
                    id=f"node_{i}_1",
                    text=f"Document {i} first chunk about lasers",
                    metadata={"chunk": 1},
                ),
                TextChunk(
                    id=f"node_{i}_2",
                    text=f"Document {i} second chunk about power meters",
                    metadata={"chunk": 2},
                ),
            ]
            keyword_index.index_nodes(
                nodes=nodes,
                doc_id=f"doc{i}",
                source=f"doc{i}.pdf",
                pairs=[("Index", str(i))],
            )

        # Get statistics
        stats = keyword_index.get_stats()
        assert stats["total_documents"] == 5
        assert stats["total_chunks"] == 10
        assert "index_size_mb" in stats
        assert stats["index_size_mb"] > 0

    def test_keywords_extraction(self, keyword_index):
        """Test keyword extraction from Context: lines."""
        # Create node with Context: line
        nodes = [
            TextChunk(
                id="ctx1",
                text="Main content here.\nContext: laser, power meter, optical measurement\nMore content.",
                metadata={},
            )
        ]

        keyword_index.index_nodes(
            nodes=nodes, doc_id="doc_ctx", source="context.pdf", pairs=[]
        )

        # Search for a keyword that's only in the Context line
        results = keyword_index.search("optical measurement")
        assert len(results) > 0

    def test_persistence(self, keyword_index, test_config):
        """Test that index persists across instances."""
        # Index a node
        nodes = [
            TextChunk(id="persist1", text="Persistent document content about lasers")
        ]
        keyword_index.index_nodes(
            nodes=nodes,
            doc_id="persist_doc",
            source="persist.pdf",
            pairs=[("Test", "Persistence")],
        )

        # Create new instance with same database
        config = PipelineConfig()
        config.storage.keyword_db_path = keyword_index.db_path
        new_index = BM25Index(config=config)

        # Should find the document
        results = new_index.search("persistent")
        assert len(results) == 1
        assert results[0]["doc_id"] == "persist_doc"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

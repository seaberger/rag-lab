"""
Unit tests for Storage Manager component.

Tests cover storage operations, datasheet extraction, and artifact management.
"""

import json
import sys
import tempfile
import uuid
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from storage.datasheet import DatasheetExtractor, DatasheetPair
from storage.manager import StorageManager

from utils.config import PipelineConfig


class TestStorageManager:
    """Test suite for StorageManager."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test storage."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def config(self, temp_dir):
        """Create test configuration."""
        config = PipelineConfig()
        config.storage.base_path = str(temp_dir)
        config.storage.format = "jsonl"
        return config

    @pytest.fixture
    def storage_manager(self, config):
        """Create test storage manager."""
        return StorageManager(config=config)

    def test_initialization(self, storage_manager, temp_dir):
        """Test storage manager initialization."""
        assert storage_manager.base_path == Path(temp_dir)
        assert storage_manager.format == "jsonl"
        assert storage_manager.base_path.exists()

    def test_save_document_jsonl(self, storage_manager):
        """Test saving document in JSONL format."""
        doc_id = str(uuid.uuid4())
        document_data = {
            "doc_id": doc_id,
            "source": "test.pdf",
            "content": "Test content",
            "metadata": {"pages": 1},
            "chunks": [
                {"id": "chunk1", "text": "First chunk"},
                {"id": "chunk2", "text": "Second chunk"}
            ]
        }

        # Save document
        result = storage_manager.save_document(doc_id, document_data)

        assert result

        # Verify file was created
        expected_path = storage_manager.base_path / f"{doc_id}.jsonl"
        assert expected_path.exists()

        # Verify content
        with open(expected_path) as f:
            lines = f.readlines()
            assert len(lines) == 1
            saved_data = json.loads(lines[0])
            assert saved_data["doc_id"] == doc_id
            assert saved_data["source"] == "test.pdf"

    def test_load_document(self, storage_manager):
        """Test loading a saved document."""
        doc_id = str(uuid.uuid4())
        document_data = {
            "doc_id": doc_id,
            "source": "test.pdf",
            "content": "Test content"
        }

        # Save document first
        storage_manager.save_document(doc_id, document_data)

        # Load it back
        loaded_data = storage_manager.load_document(doc_id)

        assert loaded_data is not None
        assert loaded_data["doc_id"] == doc_id
        assert loaded_data["source"] == "test.pdf"
        assert loaded_data["content"] == "Test content"

    def test_load_nonexistent_document(self, storage_manager):
        """Test loading a document that doesn't exist."""
        result = storage_manager.load_document("nonexistent_id")
        assert result is None

    def test_delete_document(self, storage_manager):
        """Test deleting a document."""
        doc_id = str(uuid.uuid4())
        document_data = {"doc_id": doc_id, "content": "Test"}

        # Save document
        storage_manager.save_document(doc_id, document_data)
        assert storage_manager.document_exists(doc_id)

        # Delete it
        result = storage_manager.delete_document(doc_id)
        assert result
        assert not storage_manager.document_exists(doc_id)

    def test_list_documents(self, storage_manager):
        """Test listing all documents."""
        # Save multiple documents
        doc_ids = []
        for i in range(3):
            doc_id = str(uuid.uuid4())
            doc_ids.append(doc_id)
            storage_manager.save_document(doc_id, {
                "doc_id": doc_id,
                "content": f"Document {i}"
            })

        # List documents
        documents = storage_manager.list_documents()

        assert len(documents) == 3
        for doc_id in doc_ids:
            assert doc_id in documents

    def test_get_statistics(self, storage_manager):
        """Test getting storage statistics."""
        # Save some documents
        for i in range(5):
            doc_id = str(uuid.uuid4())
            storage_manager.save_document(doc_id, {
                "doc_id": doc_id,
                "content": f"Document {i}" * 100  # Make it bigger
            })

        # Get statistics
        stats = storage_manager.get_statistics()

        assert stats["total_documents"] == 5
        assert stats["total_size_mb"] > 0
        assert stats["format"] == "jsonl"

    def test_document_exists(self, storage_manager):
        """Test checking if document exists."""
        doc_id = str(uuid.uuid4())

        # Should not exist initially
        assert not storage_manager.document_exists(doc_id)

        # Save document
        storage_manager.save_document(doc_id, {"doc_id": doc_id})

        # Should exist now
        assert storage_manager.document_exists(doc_id)

    def test_save_with_compression(self, storage_manager):
        """Test saving with compression enabled."""
        storage_manager.compression = "gzip"
        doc_id = str(uuid.uuid4())

        large_content = "Large content " * 1000
        document_data = {
            "doc_id": doc_id,
            "content": large_content
        }

        # Save with compression
        result = storage_manager.save_document(doc_id, document_data)
        assert result

        # File should be smaller than uncompressed
        file_path = storage_manager.base_path / f"{doc_id}.jsonl.gz"
        assert file_path.exists()

    def test_batch_save(self, storage_manager):
        """Test batch saving multiple documents."""
        documents = []
        for i in range(10):
            documents.append({
                "doc_id": str(uuid.uuid4()),
                "content": f"Document {i}"
            })

        # Batch save
        results = storage_manager.batch_save(documents)

        assert results["success"] == 10
        assert results["failed"] == 0

    def test_export_to_json(self, storage_manager):
        """Test exporting all documents to single JSON file."""
        # Save some documents
        doc_ids = []
        for i in range(3):
            doc_id = str(uuid.uuid4())
            doc_ids.append(doc_id)
            storage_manager.save_document(doc_id, {
                "doc_id": doc_id,
                "content": f"Document {i}"
            })

        # Export to JSON
        export_path = storage_manager.base_path / "export.json"
        result = storage_manager.export_to_json(export_path)

        assert result
        assert export_path.exists()

        # Verify exported content
        with open(export_path) as f:
            exported_data = json.load(f)
            assert len(exported_data) == 3

    def test_validate_document_data(self, storage_manager):
        """Test document data validation."""
        # Valid document
        valid_doc = {
            "doc_id": "123",
            "source": "test.pdf",
            "content": "Test"
        }
        assert storage_manager.validate_document(valid_doc)

        # Invalid documents
        invalid_docs = [
            {},  # Empty
            {"source": "test.pdf"},  # Missing doc_id
            {"doc_id": "123"},  # Missing source
        ]

        for doc in invalid_docs:
            assert not storage_manager.validate_document(doc)


class TestDatasheetExtractor:
    """Test suite for DatasheetExtractor."""

    @pytest.fixture
    def extractor(self):
        """Create test datasheet extractor."""
        with patch("storage.datasheet.OpenAI"):
            return DatasheetExtractor()

    def test_extract_pairs_from_text(self, extractor):
        """Test extracting key-value pairs from text."""
        # Mock the OpenAI response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = """
        <manufacturer>Coherent</manufacturer>
        <product>PowerMax PM10</product>
        <power_range>10mW-10W</power_range>
        """

        extractor.client.chat.completions.create = Mock(return_value=mock_response)

        # Extract pairs
        text = "PowerMax PM10 by Coherent. Power range: 10mW-10W"
        pairs = extractor.extract_pairs_from_text(text)

        assert len(pairs) == 3
        assert any(p.key == "manufacturer" and p.value == "Coherent" for p in pairs)
        assert any(p.key == "product" and p.value == "PowerMax PM10" for p in pairs)

    def test_parse_llm_response(self, extractor):
        """Test parsing LLM response with various formats."""
        # Test XML format
        xml_response = """
        <manufacturer>Coherent</manufacturer>
        <product>PM100</product>
        """
        pairs = extractor._parse_llm_response(xml_response)
        assert len(pairs) == 2

        # Test JSON format
        json_response = """
        {
            "manufacturer": "Coherent",
            "product": "PM100"
        }
        """
        pairs = extractor._parse_llm_response(json_response)
        assert len(pairs) == 2

        # Test key: value format
        kv_response = """
        manufacturer: Coherent
        product: PM100
        """
        pairs = extractor._parse_llm_response(kv_response)
        assert len(pairs) == 2

    def test_standardize_key(self, extractor):
        """Test key standardization."""
        test_cases = [
            ("Product Name", "product_name"),
            ("Power Range (W)", "power_range_w"),
            ("RS-232 Interface", "rs_232_interface"),
            ("ISO/IEC Compliance", "iso_iec_compliance")
        ]

        for input_key, expected in test_cases:
            assert extractor._standardize_key(input_key) == expected

    def test_validate_and_clean_pairs(self, extractor):
        """Test pair validation and cleaning."""
        pairs = [
            DatasheetPair("product", "PM100"),
            DatasheetPair("", "Invalid"),  # Empty key
            DatasheetPair("valid_key", ""),  # Empty value
            DatasheetPair("duplicate", "value1"),
            DatasheetPair("duplicate", "value2"),  # Duplicate key
        ]

        cleaned = extractor._validate_and_clean_pairs(pairs)

        # Should remove invalid pairs and keep first duplicate
        assert len(cleaned) == 2
        assert cleaned[0].key == "product"
        assert cleaned[1].key == "duplicate"
        assert cleaned[1].value == "value1"

    def test_error_handling(self, extractor):
        """Test error handling in extraction."""
        # Mock OpenAI to raise an exception
        extractor.client.chat.completions.create = Mock(
            side_effect=Exception("API Error")
        )

        # Should return empty list on error
        pairs = extractor.extract_pairs_from_text("Test text")
        assert pairs == []

    def test_extract_pairs_from_chunks(self, extractor):
        """Test extracting pairs from multiple chunks."""
        # Mock responses for each chunk
        extractor.extract_pairs_from_text = Mock(side_effect=[
            [DatasheetPair("product", "PM100")],
            [DatasheetPair("manufacturer", "Coherent")],
            []  # Empty result from one chunk
        ])

        chunks = ["chunk1", "chunk2", "chunk3"]
        all_pairs = extractor.extract_pairs_from_chunks(chunks)

        assert len(all_pairs) == 2
        assert extractor.extract_pairs_from_text.call_count == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

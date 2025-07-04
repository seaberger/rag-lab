"""
Unit tests for Qdrant dual-mode configuration (local vs server).
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import sys

# Add parent directories to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from src.pipeline_v3.utils.config import PipelineConfig, QdrantSettings, QdrantLocalSettings, QdrantServerSettings


class TestQdrantDualModeConfig:
    """Test Qdrant dual-mode configuration."""

    def test_default_local_mode(self):
        """Test that default configuration uses local mode."""
        config = PipelineConfig()

        assert config.qdrant.mode == "local"
        assert config.qdrant.local.path == "./qdrant_data_v3"
        assert config.qdrant.collection_name == "datasheets_v3"
        # Test legacy path property
        assert config.qdrant.path == "./qdrant_data_v3"

    def test_server_mode_config(self):
        """Test server mode configuration."""
        config = PipelineConfig()
        config.qdrant.mode = "server"
        config.qdrant.server.host = "qdrant.example.com"
        config.qdrant.server.port = 6333
        config.qdrant.server.api_key = "test-key"  # pragma: allowlist secret

        assert config.qdrant.mode == "server"
        assert config.qdrant.server.host == "qdrant.example.com"
        assert config.qdrant.server.port == 6333
        assert config.qdrant.server.api_key == "test-key"  # pragma: allowlist secret

    def test_yaml_parsing(self):
        """Test that YAML configuration is parsed correctly."""
        yaml_content = """
qdrant:
  mode: server
  local:
    path: ./custom_local_path
  server:
    host: remote.qdrant.com
    port: 6334
    api_key: secret-key  # pragma: allowlist secret
  collection_name: custom_collection
  collections:
    default: custom_collection
    finance: datasheets_finance
"""

        with patch("builtins.open", mock_open(read_data=yaml_content)):
            with patch("os.path.exists", return_value=True):
                config = PipelineConfig.from_yaml("test_config.yaml")

        assert config.qdrant.mode == "server"
        assert config.qdrant.local.path == "./custom_local_path"
        assert config.qdrant.server.host == "remote.qdrant.com"
        assert config.qdrant.server.port == 6334
        assert config.qdrant.collection_name == "custom_collection"
        assert config.qdrant.collections["finance"] == "datasheets_finance"


class TestIndexManagerDualMode:
    """Test IndexManager with dual-mode support."""

    @patch('qdrant_client.QdrantClient')
    @patch('llama_index.vector_stores.qdrant.QdrantVectorStore')
    def test_local_mode_initialization(self, mock_vector_store, mock_qdrant_client):
        """Test IndexManager initializes correctly in local mode."""
        from src.pipeline_v3.core.index_manager import IndexManager

        config = PipelineConfig()
        config.qdrant.mode = "local"

        # Mock the client instance
        mock_client_instance = Mock()
        mock_qdrant_client.return_value = mock_client_instance

        # Create IndexManager
        manager = IndexManager(config)

        # Verify local mode initialization
        mock_qdrant_client.assert_called_once_with(path=config.qdrant.local.path)
        mock_vector_store.assert_called_once()

    @patch('qdrant_client.QdrantClient')
    @patch('llama_index.vector_stores.qdrant.QdrantVectorStore')
    @patch.dict('os.environ', {'QDRANT_API_KEY': 'env-test-key'})  # pragma: allowlist secret
    def test_server_mode_initialization(self, mock_vector_store, mock_qdrant_client):
        """Test IndexManager initializes correctly in server mode."""
        from src.pipeline_v3.core.index_manager import IndexManager

        config = PipelineConfig()
        config.qdrant.mode = "server"
        config.qdrant.server.host = "test-server"
        config.qdrant.server.port = 6333
        config.qdrant.server.api_key = None  # Should use env var

        # Mock the client instance and collection check
        mock_client_instance = Mock()
        mock_collections = Mock()
        mock_collections.collections = []
        mock_client_instance.get_collections.return_value = mock_collections
        mock_qdrant_client.return_value = mock_client_instance

        # Create IndexManager
        manager = IndexManager(config)

        # Verify server mode initialization with env API key
        mock_qdrant_client.assert_called_once_with(
            host="test-server",
            port=6333,
            grpc_port=6334,
            api_key="env-test-key",  # pragma: allowlist secret
            https=False,
            timeout=30,
        )

        # Verify collection existence check
        mock_client_instance.get_collections.assert_called_once()
        mock_client_instance.create_collection.assert_called_once()

    @patch('qdrant_client.QdrantClient')
    def test_collection_creation(self, mock_qdrant_client):
        """Test collection creation when it doesn't exist."""
        from src.pipeline_v3.core.index_manager import IndexManager

        config = PipelineConfig()
        config.qdrant.mode = "server"

        # Mock client and collections
        mock_client_instance = Mock()
        mock_collections = Mock()
        mock_collections.collections = []  # No existing collections
        mock_client_instance.get_collections.return_value = mock_collections
        mock_qdrant_client.return_value = mock_client_instance

        # Create IndexManager
        manager = IndexManager(config)

        # Verify collection was created
        mock_client_instance.create_collection.assert_called_once()
        call_args = mock_client_instance.create_collection.call_args
        assert call_args[1]['collection_name'] == config.qdrant.collection_name
        assert call_args[1]['vectors_config'].size == config.openai.dimensions


def mock_open(read_data=""):
    """Helper to create a mock file open."""
    import io
    from unittest.mock import MagicMock

    file_object = io.StringIO(read_data)
    file_object.__enter__ = lambda self: self
    file_object.__exit__ = lambda *args: None

    mock = MagicMock(return_value=file_object)
    mock.__enter__ = lambda self: file_object
    mock.__exit__ = lambda *args: None

    return mock

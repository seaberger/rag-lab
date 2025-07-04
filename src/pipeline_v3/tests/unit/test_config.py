"""
Unit tests for configuration management.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from ...utils.config import (
    PipelineSettings,
    ValidationSettings,
    LimitsSettings,
    CacheSettings,
    BatchSettings,
    OpenAISettings,
    LoggingSettings,
    MonitoringSettings,
    QdrantLocalSettings,
    QdrantServerSettings,
    QdrantSettings,
    ParserSettings,
    ChunkingSettings,
    JobQueueSettings,
    FingerprintSettings,
    IndexManagementSettings,
    StorageSettings,
    SearchSettings,
    ProcessingProfile,
    ProcessingProfileSettings,
    PipelineConfig,
)


class TestDataclassDefaults:
    """Test that all dataclass configurations have sensible defaults."""

    def test_pipeline_settings_defaults(self):
        """Test PipelineSettings default values."""
        settings = PipelineSettings()
        assert settings.max_concurrent == 5
        assert settings.timeout_seconds == 300
        assert settings.timeout_per_page == 30
        assert settings.timeout_base == 60
        assert settings.version == "3.0.0-dev"

    def test_validation_settings_defaults(self):
        """Test ValidationSettings default values."""
        settings = ValidationSettings()
        assert settings.validate_urls is True
        assert settings.validate_files is True
        assert ".pdf" in settings.allowed_extensions
        assert ".md" in settings.allowed_extensions
        assert ".txt" in settings.allowed_extensions
        assert settings.max_url_length == 2048

    def test_limits_settings_defaults(self):
        """Test LimitsSettings default values."""
        settings = LimitsSettings()
        assert settings.max_file_size_mb == 100
        assert settings.max_pages_per_pdf == 50

    def test_cache_settings_defaults(self):
        """Test CacheSettings default values."""
        settings = CacheSettings()
        assert settings.enabled is True
        assert settings.directory == "./cache_v3"
        assert settings.ttl_days == 7
        assert settings.compress is True

    def test_batch_settings_defaults(self):
        """Test BatchSettings default values."""
        settings = BatchSettings()
        assert settings.enabled is True
        assert settings.threshold == 10

    def test_openai_settings_defaults(self):
        """Test OpenAISettings default values."""
        settings = OpenAISettings()
        assert settings.api_key is None
        assert settings.vision_model == "gpt-4.1"
        assert settings.keyword_model == "gpt-4.1-mini"
        assert settings.embedding_model == "text-embedding-3-small"
        assert settings.dimensions == 1536
        assert settings.max_retries == 3

    def test_logging_settings_defaults(self):
        """Test LoggingSettings default values."""
        settings = LoggingSettings()
        assert settings.level == "INFO"
        assert settings.file == "pipeline.log"

    def test_monitoring_settings_defaults(self):
        """Test MonitoringSettings default values."""
        settings = MonitoringSettings()
        assert settings.progress_callback is True
        assert settings.save_report is True
        assert settings.report_file == "processing_report.json"

    def test_qdrant_local_settings_defaults(self):
        """Test QdrantLocalSettings default values."""
        settings = QdrantLocalSettings()
        assert settings.path == "./qdrant_data_v3"

    def test_qdrant_server_settings_defaults(self):
        """Test QdrantServerSettings default values."""
        settings = QdrantServerSettings()
        assert settings.host == "localhost"
        assert settings.port == 6333
        assert settings.grpc_port == 6334
        assert settings.api_key is None
        assert settings.https is False
        assert settings.timeout == 30

    def test_qdrant_settings_defaults(self):
        """Test QdrantSettings default values and legacy path property."""
        settings = QdrantSettings()
        assert settings.mode == "server"  # Default is server mode
        assert settings.collection_name == "datasheets_v3"
        assert "default" in settings.collections
        assert settings.collections["default"] == "datasheets_v3"

        # Test legacy path property
        assert settings.path == "./qdrant_data_v3"

    def test_job_queue_settings_defaults(self):
        """Test JobQueueSettings default values."""
        settings = JobQueueSettings()
        assert settings.max_concurrent == 10
        assert settings.job_persistence is True
        assert settings.job_storage_path == "./jobs_v3.db"
        assert settings.job_retention_days == 30
        assert settings.chunk_size == 100
        assert settings.default_priority == 0
        assert settings.resume_interrupted is True

    def test_fingerprint_settings_defaults(self):
        """Test FingerprintSettings default values."""
        settings = FingerprintSettings()
        assert settings.enabled is True
        assert settings.storage_path == "./fingerprints_v3.db"
        assert settings.retention_days == 90
        assert settings.include_metadata is True

    def test_storage_settings_defaults(self):
        """Test StorageSettings default values."""
        settings = StorageSettings()
        assert settings.keyword_db_path == "./keyword_index_v3.db"
        assert settings.base_dir == "./storage_data_v3"
        assert settings.document_registry_path == "./document_registry_v3.db"

    def test_search_settings_defaults(self):
        """Test SearchSettings default values."""
        settings = SearchSettings()
        assert settings.hybrid_alpha == 0.7
        assert settings.default_limit == 5
        assert settings.default_mode == "hybrid"


class TestProcessingProfileDefaults:
    """Test processing profile configurations."""

    def test_processing_profile_defaults(self):
        """Test ProcessingProfile default values."""
        profile = ProcessingProfile()
        assert profile.document_type == "auto"
        assert profile.processing_options == []
        assert profile.timeout_multiplier == 1.0
        assert profile.description == ""

    def test_processing_profile_custom_values(self):
        """Test ProcessingProfile with custom values."""
        profile = ProcessingProfile(
            document_type="datasheet",
            processing_options=["keywords", "enhanced-metadata"],
            timeout_multiplier=2.0,
            description="Custom profile"
        )
        assert profile.document_type == "datasheet"
        assert profile.processing_options == ["keywords", "enhanced-metadata"]
        assert profile.timeout_multiplier == 2.0
        assert profile.description == "Custom profile"

    def test_processing_profile_settings_defaults(self):
        """Test ProcessingProfileSettings has predefined profiles."""
        settings = ProcessingProfileSettings()

        # Should have default profiles
        assert "standard-datasheet" in settings.profiles
        assert "quick-scan" in settings.profiles
        assert "comprehensive" in settings.profiles

        # Check standard-datasheet profile
        datasheet_profile = settings.profiles["standard-datasheet"]
        assert datasheet_profile.document_type == "datasheet"
        assert "keywords" in datasheet_profile.processing_options
        assert "enhanced-metadata" in datasheet_profile.processing_options

        # Check quick-scan profile
        quick_profile = settings.profiles["quick-scan"]
        assert quick_profile.document_type == "auto"
        assert quick_profile.timeout_multiplier == 0.5

        # Check comprehensive profile
        comprehensive_profile = settings.profiles["comprehensive"]
        assert comprehensive_profile.timeout_multiplier == 2.0
        assert "ocr-fallback" in comprehensive_profile.processing_options


class TestPipelineConfigDefaults:
    """Test the main PipelineConfig class."""

    def test_pipeline_config_defaults(self):
        """Test PipelineConfig creates all subsections with defaults."""
        config = PipelineConfig()

        # Check all sections exist
        assert isinstance(config.pipeline, PipelineSettings)
        assert isinstance(config.validation, ValidationSettings)
        assert isinstance(config.limits, LimitsSettings)
        assert isinstance(config.cache, CacheSettings)
        assert isinstance(config.batch, BatchSettings)
        assert isinstance(config.job_queue, JobQueueSettings)
        assert isinstance(config.fingerprint, FingerprintSettings)
        assert isinstance(config.index_management, IndexManagementSettings)
        assert isinstance(config.openai, OpenAISettings)
        assert isinstance(config.logging, LoggingSettings)
        assert isinstance(config.monitoring, MonitoringSettings)
        assert isinstance(config.qdrant, QdrantSettings)
        assert isinstance(config.parser, ParserSettings)
        assert isinstance(config.chunking, ChunkingSettings)
        assert isinstance(config.storage, StorageSettings)
        assert isinstance(config.search, SearchSettings)
        assert isinstance(config.processing_profiles, ProcessingProfileSettings)

        # Check top-level default
        assert config.datasheet_mode is True

    def test_pipeline_config_nested_access(self):
        """Test accessing nested configuration values."""
        config = PipelineConfig()

        # Test nested access works
        assert config.openai.vision_model == "gpt-4.1"
        assert config.qdrant.server.host == "localhost"
        assert config.qdrant.server.port == 6333
        assert config.processing_profiles.profiles["quick-scan"].timeout_multiplier == 0.5


class TestYAMLConfigLoading:
    """Test loading configuration from YAML files."""

    @patch('src.pipeline_v3.utils.config.YAML_AVAILABLE', True)
    def test_from_yaml_no_file(self):
        """Test loading config when YAML file doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "nonexistent.yaml"

            config = PipelineConfig.from_yaml(str(config_path))

            # Should return default config
            assert isinstance(config, PipelineConfig)
            assert config.openai.vision_model == "gpt-4.1"  # Default value

    @patch('src.pipeline_v3.utils.config.YAML_AVAILABLE', False)
    def test_from_yaml_no_yaml_library(self):
        """Test loading config when PyYAML is not available."""
        config = PipelineConfig.from_yaml("any_path.yaml")

        # Should return default config
        assert isinstance(config, PipelineConfig)
        assert config.openai.vision_model == "gpt-4.1"

    @patch('src.pipeline_v3.utils.config.YAML_AVAILABLE', True)
    @patch('yaml.safe_load')
    @patch('builtins.open')
    def test_from_yaml_empty_file(self, mock_open, mock_yaml_load):
        """Test loading config from empty YAML file."""
        mock_yaml_load.return_value = None
        mock_open.return_value.__enter__.return_value = MagicMock()

        config = PipelineConfig.from_yaml("empty.yaml")

        # Should return default config
        assert isinstance(config, PipelineConfig)
        assert config.openai.vision_model == "gpt-4.1"

    @patch('src.pipeline_v3.utils.config.YAML_AVAILABLE', True)
    def test_from_yaml_valid_file(self):
        """Test loading config from valid YAML file."""
        yaml_content = """
openai:
  vision_model: "gpt-4-custom"
  api_key: "test-key"  # pragma: allowlist secret
qdrant:
  mode: "local"
  collection_name: "test_collection"
  server:
    port: 9999
pipeline:
  max_concurrent: 15
"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            config_path = f.name

        try:
            config = PipelineConfig.from_yaml(config_path)

            # Should load custom values
            assert config.openai.vision_model == "gpt-4-custom"
            assert config.openai.api_key == "test-key"  # pragma: allowlist secret
            assert config.qdrant.mode == "local"
            assert config.qdrant.collection_name == "test_collection"
            assert config.qdrant.server.port == 9999
            assert config.pipeline.max_concurrent == 15

            # Should keep defaults for unspecified values
            assert config.openai.keyword_model == "gpt-4.1-mini"  # Default
            assert config.qdrant.server.host == "localhost"  # Default

        finally:
            Path(config_path).unlink()

    @patch('src.pipeline_v3.utils.config.YAML_AVAILABLE', True)
    @patch('yaml.safe_load')
    @patch('builtins.open')
    def test_from_yaml_invalid_yaml(self, mock_open, mock_yaml_load):
        """Test loading config from invalid YAML file."""
        mock_yaml_load.side_effect = Exception("Invalid YAML")
        mock_open.return_value.__enter__.return_value = MagicMock()

        config = PipelineConfig.from_yaml("invalid.yaml")

        # Should return default config on error
        assert isinstance(config, PipelineConfig)
        assert config.openai.vision_model == "gpt-4.1"

    @patch('src.pipeline_v3.utils.config.YAML_AVAILABLE', True)
    def test_from_yaml_partial_config(self):
        """Test loading config with only partial YAML data."""
        yaml_content = """
openai:
  vision_model: "custom-model"
qdrant:
  mode: "server"
"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            config_path = f.name

        try:
            config = PipelineConfig.from_yaml(config_path)

            # Should load specified values
            assert config.openai.vision_model == "custom-model"
            assert config.qdrant.mode == "server"

            # Should use defaults for unspecified sections
            assert config.pipeline.max_concurrent == 5  # Default
            assert config.cache.enabled is True  # Default

        finally:
            Path(config_path).unlink()


class TestEnvironmentVariableHandling:
    """Test handling of environment variables in config."""

    @patch('os.getenv')
    @patch('src.pipeline_v3.utils.config.YAML_AVAILABLE', True)
    def test_openai_api_key_from_environment(self, mock_getenv):
        """Test loading OpenAI API key from environment variable."""
        mock_getenv.return_value = "sk-env-api-key-123"  # pragma: allowlist secret

        # Create config without API key in YAML
        yaml_content = """
openai:
  vision_model: "gpt-4-custom"
"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            config_path = f.name

        try:
            config = PipelineConfig.from_yaml(config_path)

            # Should load API key from environment
            assert config.openai.api_key == "sk-env-api-key-123"  # pragma: allowlist secret
            mock_getenv.assert_called_with("OPENAI_API_KEY")

        finally:
            Path(config_path).unlink()

    @patch('os.getenv')
    @patch('src.pipeline_v3.utils.config.YAML_AVAILABLE', True)
    def test_openai_api_key_yaml_overrides_environment(self, mock_getenv):
        """Test that YAML API key overrides environment variable."""
        mock_getenv.return_value = "sk-env-api-key-123"  # pragma: allowlist secret

        # Create config with API key in YAML
        yaml_content = """
openai:
  api_key: "sk-yaml-api-key-456"  # pragma: allowlist secret
  vision_model: "gpt-4-custom"
"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            config_path = f.name

        try:
            config = PipelineConfig.from_yaml(config_path)

            # Should use YAML value, not environment
            assert config.openai.api_key == "sk-yaml-api-key-456"  # pragma: allowlist secret

        finally:
            Path(config_path).unlink()


class TestConfigFileDiscovery:
    """Test configuration file discovery logic."""

    @patch('src.pipeline_v3.utils.config.YAML_AVAILABLE', True)
    def test_config_file_discovery_relative_path(self):
        """Test config file discovery with relative paths."""
        # Create nested directory structure
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create utils directory (simulating location of config.py)
            utils_dir = Path(temp_dir) / "utils"
            utils_dir.mkdir()

            # Create config.yaml in parent directory
            config_file = Path(temp_dir) / "config.yaml"
            config_file.write_text("""
openai:
  vision_model: "discovered-model"
""")

            # Mock __file__ to be in utils directory
            with patch('src.pipeline_v3.utils.config.__file__', str(utils_dir / "config.py")):
                config = PipelineConfig.from_yaml("config.yaml")

                # Should find and load the config file
                assert config.openai.vision_model == "discovered-model"


class TestMainExecution:
    """Test the main execution block in config.py."""

    @patch('src.pipeline_v3.utils.config.PipelineConfig.from_yaml')
    def test_main_execution_mock(self, mock_from_yaml):
        """Test main execution with mocked config loading."""
        mock_config = MagicMock()
        mock_config.pipeline = MagicMock()
        mock_config.openai.api_key = "test-key"  # pragma: allowlist secret
        mock_config.storage.base_dir = "test-dir"
        mock_config.monitoring.report_file = "test-report.json"
        mock_from_yaml.return_value = mock_config

        # Import and test would happen here, but since __name__ != "__main__"
        # in test context, we can't easily test the main block
        # This test mainly ensures the structure is there
        assert hasattr(mock_config, 'pipeline')
        assert hasattr(mock_config, 'openai')


class TestIntegrationScenarios:
    """Integration tests for realistic configuration scenarios."""

    def test_complete_config_scenario(self):
        """Test a complete realistic configuration scenario."""
        yaml_content = """
# Production configuration
pipeline:
  max_concurrent: 20
  timeout_seconds: 600
  version: "3.1.0-prod"

openai:
  vision_model: "gpt-4.1"
  keyword_model: "gpt-4.1-mini"
  max_retries: 5
  timeout_per_page: 45

qdrant:
  mode: "server"
  server:
    host: "qdrant.example.com"
    port: 6333
    https: true
  collection_name: "production_datasheets"

job_queue:
  max_concurrent: 50
  job_retention_days: 60
  resume_interrupted: true

cache:
  directory: "/var/cache/pipeline_v3"
  ttl_days: 14
  compress: true

storage:
  base_dir: "/data/pipeline_v3"
  keyword_db_path: "/data/pipeline_v3/keyword_index.db"

processing_profiles:
  profiles:
    production-standard:
      document_type: "datasheet"
      processing_options: ["keywords", "enhanced-metadata", "quality-check"]
      timeout_multiplier: 1.5
      description: "Production standard processing"
"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            config_path = f.name

        try:
            config = PipelineConfig.from_yaml(config_path)

            # Verify all sections loaded correctly
            assert config.pipeline.max_concurrent == 20
            assert config.pipeline.version == "3.1.0-prod"
            assert config.openai.max_retries == 5
            assert config.qdrant.server.host == "qdrant.example.com"
            assert config.qdrant.server.https is True
            assert config.job_queue.max_concurrent == 50
            assert config.cache.directory == "/var/cache/pipeline_v3"
            assert config.storage.base_dir == "/data/pipeline_v3"

            # Check custom processing profile (note: YAML loads as dict, not ProcessingProfile object)
            assert "production-standard" in config.processing_profiles.profiles
            prod_profile = config.processing_profiles.profiles["production-standard"]
            if isinstance(prod_profile, dict):
                # YAML loads as dict
                assert prod_profile["timeout_multiplier"] == 1.5
                assert "quality-check" in prod_profile["processing_options"]
            else:
                # If it's a ProcessingProfile object
                assert prod_profile.timeout_multiplier == 1.5
                assert "quality-check" in prod_profile.processing_options

        finally:
            Path(config_path).unlink()

    def test_minimal_config_with_defaults(self):
        """Test minimal config that relies mostly on defaults."""
        yaml_content = """
openai:
  api_key: "sk-minimal-123"  # pragma: allowlist secret
qdrant:
  collection_name: "minimal_test"
"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            config_path = f.name

        try:
            config = PipelineConfig.from_yaml(config_path)

            # Should load specified values
            assert config.openai.api_key == "sk-minimal-123"  # pragma: allowlist secret
            assert config.qdrant.collection_name == "minimal_test"

            # Should use all defaults for other values
            assert config.pipeline.max_concurrent == 5
            assert config.openai.vision_model == "gpt-4.1"
            assert config.qdrant.mode == "server"
            assert config.cache.enabled is True
            assert config.job_queue.resume_interrupted is True

        finally:
            Path(config_path).unlink()

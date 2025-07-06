import os
from dataclasses import dataclass, field

try:
    import yaml

    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


@dataclass
class PipelineSettings:
    max_concurrent: int = 5
    timeout_seconds: int = 300
    timeout_per_page: int = 30  # Seconds per PDF page for vision parsing
    timeout_base: int = 60  # Base timeout in seconds
    version: str = "3.0.0-dev"


@dataclass
class ValidationSettings:
    validate_urls: bool = True
    validate_files: bool = True
    allowed_extensions: list[str] = field(
        default_factory=lambda: [".pdf", ".md", ".txt", ".markdown", ".docx", ".pptx"]
    )
    max_url_length: int = 2048


@dataclass
class LimitsSettings:
    max_file_size_mb: int = 100
    max_pages_per_pdf: int = 50


@dataclass
class CacheSettings:
    enabled: bool = True
    directory: str = "./cache_v3"
    ttl_days: int = 7
    compress: bool = True


@dataclass
class BatchSettings:
    enabled: bool = True
    threshold: int = 10


@dataclass
class OpenAISettings:
    api_key: str | None = None
    vision_model: str = "gpt-4.1"
    keyword_model: str = "gpt-4.1-mini"
    embedding_model: str = "text-embedding-3-small"
    dimensions: int = 1536
    max_retries: int = 3
    timeout_per_page: int = 30  # Seconds per page for vision API calls
    timeout_base: int = 60  # Base timeout for API calls


@dataclass
class LoggingSettings:
    level: str = "INFO"
    file: str = "pipeline.log"


@dataclass
class MonitoringSettings:
    progress_callback: bool = True
    save_report: bool = True
    report_file: str = "processing_report.json"


@dataclass
class QdrantLocalSettings:
    path: str = "./qdrant_data_v3"


@dataclass
class QdrantServerSettings:
    host: str = "localhost"
    port: int = 6333
    grpc_port: int = 6334
    api_key: str | None = None
    https: bool = False
    timeout: int = 30


@dataclass
class QdrantSettings:
    mode: str = "server"  # "local" or "server" - DEFAULT NOW SERVER
    local: QdrantLocalSettings = field(default_factory=QdrantLocalSettings)
    server: QdrantServerSettings = field(default_factory=QdrantServerSettings)
    collection_name: str = "datasheets_v3"
    collections: dict = field(default_factory=lambda: {"default": "datasheets_v3"})

    # Legacy support for path attribute
    @property
    def path(self) -> str:
        return self.local.path


@dataclass
class ParserSettings:
    datasheet_prompt_path: str = "datasheet_parsing_prompt.md"
    generic_prompt_path: str = "generic_parsing_prompt.md"


@dataclass
class ChunkingSettings:
    chunk_size: int = 1024
    chunk_overlap: int = 128


@dataclass
class JobQueueSettings:  # NEW in v3
    max_concurrent: int = 10
    job_persistence: bool = True
    job_storage_path: str = "./jobs_v3.db"
    job_retention_days: int = 30
    chunk_size: int = 100
    default_priority: int = 0
    resume_interrupted: bool = True


@dataclass
class FingerprintSettings:  # NEW in v3
    enabled: bool = True
    storage_path: str = "./fingerprints_v3.db"
    retention_days: int = 90
    include_metadata: bool = True


@dataclass
class IndexManagementSettings:  # NEW in v3
    consistency_checks: bool = True
    auto_backup: bool = False
    backup_path: str = "./backups"
    backup_retention_days: int = 90
    rebuild_on_corruption: bool = True


@dataclass
class StorageSettings:  # Enhanced for v3
    keyword_db_path: str = "./keyword_index_v3.db"
    base_dir: str = "./storage_data_v3"
    document_registry_path: str = "./document_registry_v3.db"  # NEW in v3


@dataclass
class SearchSettings:
    hybrid_alpha: float = 0.7  # Balance between vector (0.0) and keyword (1.0) search
    default_limit: int = 5  # Default number of search results
    default_mode: str = "hybrid"  # Default search mode: hybrid, vector, or keyword


@dataclass
class ProcessingProfile:
    """Defines a reusable processing configuration profile."""

    document_type: str = "auto"
    processing_options: list[str] = field(default_factory=list)
    timeout_multiplier: float = 1.0  # Multiply default timeout
    description: str = ""


@dataclass
class ProcessingProfileSettings:
    """Collection of named processing profiles."""

    profiles: dict[str, ProcessingProfile] = field(
        default_factory=lambda: {
            "standard-datasheet": ProcessingProfile(
                document_type="datasheet",
                processing_options=["keywords", "enhanced-metadata"],
                description="Standard profile for technical datasheets with keyword enhancement",
            ),
            "quick-scan": ProcessingProfile(
                document_type="auto",
                processing_options=["fast-mode"],
                timeout_multiplier=0.5,
                description="Fast processing for quick document scanning",
            ),
            "comprehensive": ProcessingProfile(
                document_type="auto",
                processing_options=["keywords", "enhanced-metadata", "ocr-fallback"],
                timeout_multiplier=2.0,
                description="Thorough processing with all enhancements",
            ),
        }
    )


@dataclass
class PostgreSQLSettings:
    """PostgreSQL database configuration settings."""

    # Connection settings
    host: str = "localhost"
    port: int = 5432
    database: str = "rag_lab_db"
    user: str = "rag_lab_user"
    password: str = ""  # Should be loaded from environment variable
    ssl_mode: str = "prefer"  # disable, allow, prefer, require, verify-ca, verify-full

    # Connection pooling
    min_connections: int = 10
    max_connections: int = 100
    connection_timeout: int = 30  # seconds
    idle_timeout: int = 600  # seconds (10 minutes)

    # Performance settings
    statement_timeout: int = 300000  # milliseconds (5 minutes)
    lock_timeout: int = 10000  # milliseconds (10 seconds)

    # Multi-tenancy preparation
    enable_rls: bool = True  # Row Level Security
    default_schema: str = "public"
    default_tenant_id: str = "00000000-0000-0000-0000-000000000000"

    # Schema names
    registry_schema: str = "registry"
    search_schema: str = "search"
    jobs_schema: str = "jobs"
    fingerprints_schema: str = "fingerprints"


@dataclass
class DatabaseSettings:
    """Database backend configuration."""

    backend: str = "sqlite"  # "sqlite" or "postgresql"
    postgresql: PostgreSQLSettings = field(default_factory=PostgreSQLSettings)

    # Migration settings
    auto_migrate: bool = True
    migration_batch_size: int = 1000
    migration_timeout: int = 3600  # seconds (1 hour)

    # Dual-mode settings
    enable_fallback: bool = False  # Fall back to SQLite if PostgreSQL fails
    log_queries: bool = False  # Log all database queries for debugging


@dataclass
class PipelineConfig:
    pipeline: PipelineSettings = field(default_factory=PipelineSettings)
    validation: ValidationSettings = field(default_factory=ValidationSettings)
    limits: LimitsSettings = field(default_factory=LimitsSettings)
    cache: CacheSettings = field(default_factory=CacheSettings)
    batch: BatchSettings = field(default_factory=BatchSettings)
    job_queue: JobQueueSettings = field(default_factory=JobQueueSettings)  # NEW in v3
    fingerprint: FingerprintSettings = field(default_factory=FingerprintSettings)  # NEW in v3
    index_management: IndexManagementSettings = field(
        default_factory=IndexManagementSettings
    )  # NEW in v3
    openai: OpenAISettings = field(default_factory=OpenAISettings)
    logging: LoggingSettings = field(default_factory=LoggingSettings)
    monitoring: MonitoringSettings = field(default_factory=MonitoringSettings)
    qdrant: QdrantSettings = field(default_factory=QdrantSettings)
    parser: ParserSettings = field(default_factory=ParserSettings)
    chunking: ChunkingSettings = field(default_factory=ChunkingSettings)
    storage: StorageSettings = field(default_factory=StorageSettings)
    search: SearchSettings = field(default_factory=SearchSettings)  # NEW
    processing_profiles: ProcessingProfileSettings = field(
        default_factory=ProcessingProfileSettings
    )  # NEW
    database: DatabaseSettings = field(default_factory=DatabaseSettings)  # NEW for PostgreSQL
    datasheet_mode: bool = True

    @classmethod
    def from_yaml(cls, config_path: str = "config.yaml"):
        if not YAML_AVAILABLE:
            print("Warning: PyYAML not available. Using default settings.")
            return cls()

        # Try to find the config file relative to this script, then parent, then grandparent
        # This helps if the script consuming PipelineConfig is in a subdirectory like 'pipeline' or 'search'
        # or if utils/config.py itself is run for testing.

        # Default to the provided config_path, assuming it's relative to CWD or absolute
        abs_config_path = os.path.abspath(config_path)

        if not os.path.exists(abs_config_path):
            # If not found, try relative to this file's location (utils directory)
            utils_dir = os.path.dirname(os.path.abspath(__file__))
            path_options = [
                os.path.join(
                    utils_dir, "..", config_path
                ),  # e.g., utils/../config.yaml -> project_root/config.yaml
                # os.path.join(utils_dir, "..", "..", config_path) # e.g., utils/../../config.yaml (if utils was deeper)
            ]
            for p_opt in path_options:
                resolved_opt = os.path.abspath(p_opt)
                if os.path.exists(resolved_opt):
                    abs_config_path = resolved_opt
                    # print(f"DEBUG: Config file found at: {abs_config_path}")
                    break

        try:
            with open(abs_config_path) as f:
                config_data = yaml.safe_load(f)
            if config_data is None:  # Handle empty YAML file
                print(f"Warning: Config file '{abs_config_path}' is empty. Using default settings.")
                config_data = {}
        except FileNotFoundError:
            print(
                f"Warning: Config file '{config_path}' (resolved to '{abs_config_path}') not found. Using default settings."
            )
            config_data = {}
        except Exception as e:  # Catch yaml.YAMLError or any other error
            print(f"Error parsing YAML file '{abs_config_path}': {e}. Using default settings.")
            config_data = {}  # Fallback to default for safety

        # Helper to recursively create dataclass instances from dicts
        # Ensures that only fields defined in the dataclass are passed to its constructor
        def _create_config_from_dict(config_class, data_dict_from_yaml):
            kwargs = {}
            # Iterate over fields defined in the dataclass
            for f_info in config_class.__dataclass_fields__.values():
                fname = f_info.name
                ftype = f_info.type
                # If the field name from dataclass exists in the YAML data for this level
                if fname in data_dict_from_yaml:
                    yaml_value = data_dict_from_yaml[fname]
                    # If the field is itself a dataclass and the YAML value is a dict, recurse
                    if hasattr(ftype, "__dataclass_fields__") and isinstance(yaml_value, dict):
                        kwargs[fname] = _create_config_from_dict(ftype, yaml_value)
                    else:  # Otherwise, take the YAML value directly
                        kwargs[fname] = yaml_value
                # If fname is not in data_dict_from_yaml, it will use default_factory or default value
                # as defined in the dataclass, so no need to explicitly add it to kwargs here.
            return config_class(**kwargs)

        # Create the top-level PipelineConfig instance
        instance = _create_config_from_dict(cls, config_data)

        # Special handling for OPENAI_API_KEY from environment
        if instance.openai and instance.openai.api_key is None:
            instance.openai.api_key = os.getenv("OPENAI_API_KEY")
            if instance.openai.api_key:
                print("INFO: Loaded OPENAI_API_KEY from environment variable.")

        # Special handling for PostgreSQL password from environment
        if (
            instance.database
            and instance.database.postgresql
            and not instance.database.postgresql.password
        ):
            pg_password = os.getenv("POSTGRES_PASSWORD")
            if pg_password:
                instance.database.postgresql.password = pg_password
                print("INFO: Loaded POSTGRES_PASSWORD from environment variable.")

        return instance


if __name__ == "__main__":
    # This test assumes config.yaml is in the parent directory (src/parsing/refactored_2_1/)
    # relative to this script (src/parsing/refactored_2_1/utils/config.py)
    try:
        current_script_dir = os.path.dirname(os.path.abspath(__file__))
        # Path to config.yaml relative to this script (utils/config.py)
        # Assuming config.yaml is in src/parsing/refactored_2_1/
        project_root_config_path = os.path.join(current_script_dir, "..", "config.yaml")

        print(f"Attempting to load config from: {project_root_config_path}")
        config = PipelineConfig.from_yaml(project_root_config_path)

        print(f"--- Loaded Configuration (Testing Mode from {project_root_config_path}) ---")
        print(f"Pipeline Settings: {config.pipeline}")
        print(f"OpenAI API Key Set: {bool(config.openai.api_key)}")
        if hasattr(config, "storage"):
            print(f"Storage base_dir: {config.storage.base_dir}")
        if hasattr(config, "monitoring"):
            print(f"Monitoring report_file: {config.monitoring.report_file}")
        print("--- Test load complete ---")

    except Exception as e:
        print(f"Error during test load in utils/config.py: {e}")
        print(
            "Make sure 'config.yaml' exists in the 'src/parsing/refactored_2_1/' directory for this test."
        )

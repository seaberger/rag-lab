# Key additions to existing pipeline
class PipelineConfig:
    """Configuration from config.yaml or environment."""

    def __init__(self, config_path="config.yaml"):
        self.config = self._load_config(config_path)
        self.validate_urls = self.config.get("validation", {}).get(
            "validate_urls", True
        )
        self.max_file_size = (
            self.config.get("limits", {}).get("max_file_size_mb", 100) * 1024 * 1024
        )
        self.enable_cache = self.config.get("cache", {}).get("enabled", True)
        self.batch_threshold = self.config.get("batch", {}).get("threshold", 10)


class DocumentProcessor:
    """Improved document processing with validation and retries."""

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.cache = CacheManager() if config.enable_cache else None
        self.progress = ProgressMonitor()
        self.validator = DocumentValidator(config)

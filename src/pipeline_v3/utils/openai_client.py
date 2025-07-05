"""
OpenAI Client Factory - Centralized API Key Management

Provides centralized OpenAI client creation with proper API key handling,
error detection, and configuration management. Fixes Issue #28 by ensuring
all OpenAI clients are properly initialized with API keys.
"""

import logging
import os
from typing import Any

from openai import OpenAI

from .config import PipelineConfig

logger = logging.getLogger(__name__)


class OpenAIClientError(Exception):
    """Errors related to OpenAI client creation and configuration."""


class OpenAIClientFactory:
    """Factory for creating properly configured OpenAI clients."""

    @staticmethod
    def create_client(
        api_key: str | None = None, config: PipelineConfig | None = None, **kwargs
    ) -> OpenAI:
        """
        Create an OpenAI client with proper API key handling.

        Args:
            api_key: Explicit API key (overrides environment/config)
            config: Pipeline configuration object
            **kwargs: Additional OpenAI client parameters

        Returns:
            Configured OpenAI client

        Raises:
            OpenAIClientError: If API key cannot be found or is invalid
        """
        # Priority order for API key:
        # 1. Explicit parameter
        # 2. Config object
        # 3. Environment variable
        resolved_api_key = None

        if api_key:
            resolved_api_key = api_key
            logger.debug("Using explicit API key parameter")
        elif config and config.openai.api_key:
            resolved_api_key = config.openai.api_key
            logger.debug("Using API key from config")
        else:
            # Check environment variable
            resolved_api_key = os.getenv("OPENAI_API_KEY")
            if resolved_api_key:
                logger.debug("Using API key from environment variable")

        # Validate API key
        if not resolved_api_key:
            error_msg = (
                "OpenAI API key not found. Please set it via:\n"
                "1. Explicit parameter: create_client(api_key='your-key')\n"
                "2. Environment variable: OPENAI_API_KEY=your-key\n"
                "3. Config file with openai.api_key setting"
            )
            logger.error(error_msg)
            raise OpenAIClientError(error_msg)

        if not resolved_api_key.strip():
            error_msg = "OpenAI API key is empty or contains only whitespace"
            logger.error(error_msg)
            raise OpenAIClientError(error_msg)

        # Basic API key format validation
        if not resolved_api_key.startswith(("sk-", "sk-proj-")):
            logger.warning("API key doesn't start with expected prefix (sk- or sk-proj-)")

        # Create client with resolved API key
        try:
            client_kwargs = {"api_key": resolved_api_key, **kwargs}

            # Add timeout from config if available and not explicitly provided
            if config and not kwargs.get("timeout"):
                # Use config timeout settings for client
                timeout = getattr(config.openai, "client_timeout", 60)
                if timeout:
                    client_kwargs["timeout"] = timeout

            client = OpenAI(**client_kwargs)
            logger.info("OpenAI client created successfully")
            return client

        except Exception as e:
            error_msg = f"Failed to create OpenAI client: {e}"
            logger.exception(error_msg)
            raise OpenAIClientError(error_msg) from e

    @staticmethod
    def validate_api_key(api_key: str) -> bool:
        """
        Validate an API key by making a minimal API call.

        Args:
            api_key: API key to validate

        Returns:
            True if API key is valid, False otherwise
        """
        try:
            client = OpenAI(api_key=api_key)
            # Make a minimal API call to validate
            client.models.list()
            return True
        except Exception as e:
            logger.warning(f"API key validation failed: {e}")
            return False

    @staticmethod
    def get_api_key_info(config: PipelineConfig | None = None) -> dict[str, Any]:
        """
        Get information about the current API key configuration.

        Args:
            config: Optional pipeline configuration

        Returns:
            Dictionary with API key configuration info
        """
        info = {
            "api_key_found": False,
            "source": None,
            "key_prefix": None,
            "key_length": None,
        }

        api_key = None

        # Check config first
        if config and config.openai.api_key:
            api_key = config.openai.api_key
            info["source"] = "config"
        else:
            # Check environment
            api_key = os.getenv("OPENAI_API_KEY")
            if api_key:
                info["source"] = "environment"

        if api_key:
            info["api_key_found"] = True
            # Only show first 3-4 characters for better security
            info["key_prefix"] = api_key[:3] + "..." if len(api_key) > 3 else "***"
            info["key_length"] = len(api_key)

        return info


# Convenience functions for common use cases
def create_vision_client(config: PipelineConfig | None = None) -> OpenAI:
    """Create OpenAI client optimized for vision API calls."""
    return OpenAIClientFactory.create_client(
        config=config,
        # Add vision-specific timeouts if needed
        timeout=config.openai.timeout_base + 30 if config else 90,
    )


def create_text_client(config: PipelineConfig | None = None) -> OpenAI:
    """Create OpenAI client optimized for text API calls (chat, embeddings)."""
    return OpenAIClientFactory.create_client(
        config=config, timeout=config.openai.timeout_base if config else 60
    )


def create_embedding_client(config: PipelineConfig | None = None) -> OpenAI:
    """Create OpenAI client optimized for embedding API calls."""
    return OpenAIClientFactory.create_client(
        config=config, timeout=config.openai.timeout_base if config else 60
    )


# Legacy compatibility - deprecated but maintained for transition
def get_openai_client(config: PipelineConfig | None = None) -> OpenAI:
    """
    DEPRECATED: Use create_vision_client, create_text_client, or OpenAIClientFactory.create_client instead.

    Legacy function for backward compatibility.
    """
    logger.warning(
        "get_openai_client() is deprecated. Use OpenAIClientFactory.create_client() instead."
    )
    return OpenAIClientFactory.create_client(config=config)

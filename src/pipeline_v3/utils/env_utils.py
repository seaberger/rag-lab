"""
Environment utilities for robust .env file discovery and loading.
"""

import os
from pathlib import Path
from typing import Optional

from .common_utils import logger


def find_dotenv(start_dir: Optional[str] = None) -> Optional[str]:
    """
    Walk up from start_dir (or current working directory) to find the first .env file.
    Returns the full path if found, else None.
    
    Args:
        start_dir: Directory to start search from. If None, uses current working directory.
        
    Returns:
        Full path to .env file if found, None otherwise.
    """
    if start_dir is None:
        start_dir = os.getcwd()
        
    current_dir = os.path.abspath(start_dir)
    
    while True:
        candidate = os.path.join(current_dir, '.env')
        if os.path.isfile(candidate):
            return candidate
            
        parent = os.path.dirname(current_dir)
        if parent == current_dir:
            # Reached filesystem root, not found
            return None
        current_dir = parent


def load_environment(start_dir: Optional[str] = None, override: bool = True) -> bool:
    """
    Find and load .env file, with helpful logging.
    
    Args:
        start_dir: Directory to start search from. If None, uses current working directory.
        override: Whether to override existing environment variables.
        
    Returns:
        True if .env file was found and loaded, False otherwise.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        logger.warning("python-dotenv not installed. Skipping .env file loading.")
        return False
    
    dotenv_path = find_dotenv(start_dir)
    
    if dotenv_path:
        logger.info(f"Found .env file at: {dotenv_path}")
        success = load_dotenv(dotenv_path=dotenv_path, override=override)
        if success:
            logger.info("✅ Environment variables loaded successfully")
        else:
            logger.warning("⚠️ Failed to load environment variables")
        return success
    else:
        logger.info("No .env file found in directory tree")
        return False


def ensure_openai_key() -> bool:
    """
    Ensure OpenAI API key is available in environment.
    
    Returns:
        True if OPENAI_API_KEY is set, False otherwise.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    
    if not api_key:
        logger.error(
            "❌ OPENAI_API_KEY not found in environment variables!\n"
            "Please set it by:\n"
            "1. Adding it to a .env file: OPENAI_API_KEY=sk-...\n"
            "2. Setting it in your shell: export OPENAI_API_KEY=sk-...\n"
            "3. Passing it directly to the application"
        )
        return False
    
    if not api_key.startswith("sk-"):
        logger.warning("⚠️ OPENAI_API_KEY doesn't start with 'sk-', may be invalid")
        return False
    
    logger.info("✅ OpenAI API key found in environment")
    return True


def setup_environment(start_dir: Optional[str] = None) -> bool:
    """
    Complete environment setup: find .env, load it, and verify required keys.
    
    Args:
        start_dir: Directory to start .env search from.
        
    Returns:
        True if environment is properly set up, False otherwise.
    """
    logger.info("🔧 Setting up environment...")
    
    # Load .env file if available
    load_environment(start_dir)
    
    # Verify required environment variables
    return ensure_openai_key()
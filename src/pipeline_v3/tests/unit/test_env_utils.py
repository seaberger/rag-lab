"""
Unit tests for environment utilities.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from ...utils.env_utils import find_dotenv, load_environment, ensure_openai_key, setup_environment


class TestFindDotenv:
    """Test the find_dotenv function."""

    def test_find_dotenv_current_directory(self):
        """Test finding .env in current directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            env_file = Path(temp_dir) / ".env"
            env_file.write_text("TEST_VAR=test_value")

            result = find_dotenv(temp_dir)
            assert result == str(env_file)

    def test_find_dotenv_parent_directory(self):
        """Test finding .env in parent directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            parent_dir = Path(temp_dir)
            child_dir = parent_dir / "child"
            child_dir.mkdir()

            env_file = parent_dir / ".env"
            env_file.write_text("TEST_VAR=test_value")

            result = find_dotenv(str(child_dir))
            assert result == str(env_file)

    def test_find_dotenv_grandparent_directory(self):
        """Test finding .env in grandparent directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            grandparent_dir = Path(temp_dir)
            parent_dir = grandparent_dir / "parent"
            child_dir = parent_dir / "child"
            parent_dir.mkdir()
            child_dir.mkdir()

            env_file = grandparent_dir / ".env"
            env_file.write_text("TEST_VAR=test_value")

            result = find_dotenv(str(child_dir))
            assert result == str(env_file)

    def test_find_dotenv_not_found(self):
        """Test when .env file is not found."""
        with tempfile.TemporaryDirectory() as temp_dir:
            child_dir = Path(temp_dir) / "child"
            child_dir.mkdir()

            result = find_dotenv(str(child_dir))
            assert result is None

    def test_find_dotenv_default_cwd(self):
        """Test finding .env with default current working directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            env_file = Path(temp_dir) / ".env"
            env_file.write_text("TEST_VAR=test_value")

            with patch('os.getcwd', return_value=temp_dir):
                result = find_dotenv()
                assert result == str(env_file)

    def test_find_dotenv_reaches_filesystem_root(self):
        """Test that search stops at filesystem root."""
        # This test ensures we don't infinite loop
        result = find_dotenv("/nonexistent/very/deep/path")
        assert result is None


class TestLoadEnvironment:
    """Test the load_environment function."""

    @patch('src.pipeline_v3.utils.env_utils.find_dotenv')
    @patch('dotenv.load_dotenv')
    def test_load_environment_success(self, mock_load_dotenv, mock_find_dotenv):
        """Test successful environment loading."""
        mock_find_dotenv.return_value = "/path/to/.env"
        mock_load_dotenv.return_value = True

        result = load_environment()

        assert result is True
        mock_find_dotenv.assert_called_once_with(None)
        mock_load_dotenv.assert_called_once_with(dotenv_path="/path/to/.env", override=True)

    @patch('src.pipeline_v3.utils.env_utils.find_dotenv')
    def test_load_environment_not_found(self, mock_find_dotenv):
        """Test when .env file is not found."""
        mock_find_dotenv.return_value = None

        result = load_environment()

        assert result is False
        mock_find_dotenv.assert_called_once_with(None)

    @patch('src.pipeline_v3.utils.env_utils.find_dotenv')
    @patch('dotenv.load_dotenv')
    def test_load_environment_load_fails(self, mock_load_dotenv, mock_find_dotenv):
        """Test when dotenv loading fails."""
        mock_find_dotenv.return_value = "/path/to/.env"
        mock_load_dotenv.return_value = False

        result = load_environment()

        assert result is False

    def test_load_environment_dotenv_not_installed(self):
        """Test when python-dotenv is not installed."""
        with patch.dict('sys.modules', {'dotenv': None}):
            # Simulate ImportError
            with patch('builtins.__import__', side_effect=ImportError("No module named 'dotenv'")):
                result = load_environment()
                assert result is False

    @patch('src.pipeline_v3.utils.env_utils.find_dotenv')
    @patch('dotenv.load_dotenv')
    def test_load_environment_custom_start_dir(self, mock_load_dotenv, mock_find_dotenv):
        """Test loading environment with custom start directory."""
        mock_find_dotenv.return_value = "/custom/path/.env"
        mock_load_dotenv.return_value = True

        result = load_environment("/custom/start/dir")

        assert result is True
        mock_find_dotenv.assert_called_once_with("/custom/start/dir")

    @patch('src.pipeline_v3.utils.env_utils.find_dotenv')
    @patch('dotenv.load_dotenv')
    def test_load_environment_no_override(self, mock_load_dotenv, mock_find_dotenv):
        """Test loading environment without override."""
        mock_find_dotenv.return_value = "/path/to/.env"
        mock_load_dotenv.return_value = True

        result = load_environment(override=False)

        assert result is True
        mock_load_dotenv.assert_called_once_with(dotenv_path="/path/to/.env", override=False)


class TestEnsureOpenaiKey:
    """Test the ensure_openai_key function."""

    def test_ensure_openai_key_valid(self):
        """Test with valid OpenAI API key."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'sk-1234567890abcdef'}):  # pragma: allowlist secret
            result = ensure_openai_key()
            assert result is True

    def test_ensure_openai_key_missing(self):
        """Test with missing OpenAI API key."""
        with patch.dict(os.environ, {}, clear=True):
            result = ensure_openai_key()
            assert result is False

    def test_ensure_openai_key_empty(self):
        """Test with empty OpenAI API key."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': ''}):
            result = ensure_openai_key()
            assert result is False

    def test_ensure_openai_key_invalid_format(self):
        """Test with invalid OpenAI API key format."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'invalid-key-format'}):  # pragma: allowlist secret
            result = ensure_openai_key()
            assert result is False

    def test_ensure_openai_key_old_format_warning(self):
        """Test with old API key format (still returns False for non-sk format)."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'pk-1234567890abcdef'}):  # pragma: allowlist secret
            result = ensure_openai_key()
            assert result is False

    def test_ensure_openai_key_edge_cases(self):
        """Test edge cases for API key validation."""
        # Just "sk-" should be valid (minimal format check)
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'sk-'}):  # pragma: allowlist secret
            result = ensure_openai_key()
            assert result is True

        # Valid minimum length
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'sk-a'}):  # pragma: allowlist secret
            result = ensure_openai_key()
            assert result is True


class TestSetupEnvironment:
    """Test the setup_environment function."""

    @patch('src.pipeline_v3.utils.env_utils.load_environment')
    @patch('src.pipeline_v3.utils.env_utils.ensure_openai_key')
    def test_setup_environment_success(self, mock_ensure_key, mock_load_env):
        """Test successful environment setup."""
        mock_load_env.return_value = True
        mock_ensure_key.return_value = True

        result = setup_environment()

        assert result is True
        mock_load_env.assert_called_once_with(None)
        mock_ensure_key.assert_called_once()

    @patch('src.pipeline_v3.utils.env_utils.load_environment')
    @patch('src.pipeline_v3.utils.env_utils.ensure_openai_key')
    def test_setup_environment_env_load_fails(self, mock_ensure_key, mock_load_env):
        """Test when environment loading fails but key check succeeds."""
        mock_load_env.return_value = False
        mock_ensure_key.return_value = True

        result = setup_environment()

        # Should still return True if key is valid, even if .env loading failed
        assert result is True
        mock_load_env.assert_called_once_with(None)
        mock_ensure_key.assert_called_once()

    @patch('src.pipeline_v3.utils.env_utils.load_environment')
    @patch('src.pipeline_v3.utils.env_utils.ensure_openai_key')
    def test_setup_environment_key_check_fails(self, mock_ensure_key, mock_load_env):
        """Test when key validation fails."""
        mock_load_env.return_value = True
        mock_ensure_key.return_value = False

        result = setup_environment()

        assert result is False
        mock_load_env.assert_called_once_with(None)
        mock_ensure_key.assert_called_once()

    @patch('src.pipeline_v3.utils.env_utils.load_environment')
    @patch('src.pipeline_v3.utils.env_utils.ensure_openai_key')
    def test_setup_environment_custom_start_dir(self, mock_ensure_key, mock_load_env):
        """Test environment setup with custom start directory."""
        mock_load_env.return_value = True
        mock_ensure_key.return_value = True

        result = setup_environment("/custom/start/dir")

        assert result is True
        mock_load_env.assert_called_once_with("/custom/start/dir")
        mock_ensure_key.assert_called_once()

    @patch('src.pipeline_v3.utils.env_utils.load_environment')
    @patch('src.pipeline_v3.utils.env_utils.ensure_openai_key')
    def test_setup_environment_both_fail(self, mock_ensure_key, mock_load_env):
        """Test when both environment loading and key validation fail."""
        mock_load_env.return_value = False
        mock_ensure_key.return_value = False

        result = setup_environment()

        assert result is False
        mock_load_env.assert_called_once_with(None)
        mock_ensure_key.assert_called_once()


class TestIntegrationScenarios:
    """Integration tests for realistic scenarios."""

    def test_real_dotenv_file_scenario(self):
        """Test with a real .env file in a temporary directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            env_file = Path(temp_dir) / ".env"
            env_file.write_text("OPENAI_API_KEY=sk-test123\nOTHER_VAR=value")  # pragma: allowlist secret

            # Test find_dotenv
            found_path = find_dotenv(temp_dir)
            assert found_path == str(env_file)

            # Test that file exists and has content
            assert Path(found_path).exists()
            content = Path(found_path).read_text()
            assert "sk-test123" in content

    def test_nested_directory_search(self):
        """Test realistic nested directory search."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create nested structure: temp/project/src/module
            project_dir = Path(temp_dir) / "project"
            src_dir = project_dir / "src"
            module_dir = src_dir / "module"

            project_dir.mkdir()
            src_dir.mkdir()
            module_dir.mkdir()

            # Put .env in project root
            env_file = project_dir / ".env"
            env_file.write_text("OPENAI_API_KEY=sk-project123")  # pragma: allowlist secret

            # Search from deep module directory
            found_path = find_dotenv(str(module_dir))
            assert found_path == str(env_file)

            # Verify it found the right file
            content = Path(found_path).read_text()
            assert "sk-project123" in content

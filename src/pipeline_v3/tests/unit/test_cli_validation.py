"""
Unit tests for CLI validation utilities.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from ...cli.utils.validation import InputValidator, ValidationError


class TestInputValidator:
    """Test the InputValidator class methods."""

    def test_validate_file_path_exists(self):
        """Test file path validation when file exists."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            file_path = f.name
        
        try:
            result = InputValidator.validate_file_path(file_path)
            assert isinstance(result, Path)
            assert result.exists()
        finally:
            Path(file_path).unlink()

    def test_validate_file_path_not_exists(self):
        """Test file path validation when file doesn't exist."""
        with pytest.raises(ValidationError, match="File does not exist"):
            InputValidator.validate_file_path("/nonexistent/file.txt")

    def test_validate_file_path_not_file(self):
        """Test file path validation when path is not a file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with pytest.raises(ValidationError, match="Path is not a file"):
                InputValidator.validate_file_path(temp_dir)

    def test_validate_file_path_no_existence_check(self):
        """Test file path validation without existence check."""
        result = InputValidator.validate_file_path("/nonexistent/file.txt", must_exist=False)
        assert isinstance(result, Path)
        assert str(result) == str(Path("/nonexistent/file.txt").resolve())

    def test_validate_directory_path_exists(self):
        """Test directory path validation when directory exists."""
        with tempfile.TemporaryDirectory() as temp_dir:
            result = InputValidator.validate_directory_path(temp_dir)
            assert isinstance(result, Path)
            assert result.exists()
            assert result.is_dir()

    def test_validate_directory_path_not_exists(self):
        """Test directory path validation when directory doesn't exist."""
        with pytest.raises(ValidationError, match="Directory does not exist"):
            InputValidator.validate_directory_path("/nonexistent/directory")

    def test_validate_directory_path_not_directory(self):
        """Test directory path validation when path is not a directory."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            file_path = f.name
        
        try:
            with pytest.raises(ValidationError, match="Path is not a directory"):
                InputValidator.validate_directory_path(file_path)
        finally:
            Path(file_path).unlink()

    def test_validate_metadata_valid(self):
        """Test metadata validation with valid input."""
        metadata_list = ["key1=value1", "key2=123", "key3={\"nested\": true}"]
        result = InputValidator.validate_metadata(metadata_list)
        
        expected = {
            "key1": "value1",
            "key2": 123,
            "key3": {"nested": True}
        }
        assert result == expected

    def test_validate_metadata_invalid_format(self):
        """Test metadata validation with invalid format."""
        with pytest.raises(ValidationError, match="Invalid metadata format"):
            InputValidator.validate_metadata(["invalid_format"])

    def test_validate_metadata_empty_key(self):
        """Test metadata validation with empty key."""
        with pytest.raises(ValidationError, match="Empty metadata key"):
            InputValidator.validate_metadata(["=value"])

    def test_validate_json_valid(self):
        """Test JSON validation with valid input."""
        json_str = '{"key": "value", "number": 42}'
        result = InputValidator.validate_json(json_str)
        assert result == {"key": "value", "number": 42}

    def test_validate_json_invalid(self):
        """Test JSON validation with invalid input."""
        with pytest.raises(ValidationError, match="Invalid JSON"):
            InputValidator.validate_json("invalid json")

    def test_validate_positive_integer_valid(self):
        """Test positive integer validation with valid input."""
        assert InputValidator.validate_positive_integer("5") == 5
        assert InputValidator.validate_positive_integer(10) == 10

    def test_validate_positive_integer_zero(self):
        """Test positive integer validation with zero."""
        with pytest.raises(ValidationError, match="must be positive"):
            InputValidator.validate_positive_integer(0)

    def test_validate_positive_integer_negative(self):
        """Test positive integer validation with negative number."""
        with pytest.raises(ValidationError, match="must be positive"):
            InputValidator.validate_positive_integer(-5)

    def test_validate_positive_integer_invalid(self):
        """Test positive integer validation with non-integer."""
        with pytest.raises(ValidationError, match="must be an integer"):
            InputValidator.validate_positive_integer("not_a_number")

    def test_validate_choice_valid(self):
        """Test choice validation with valid input."""
        choices = ["option1", "option2", "option3"]
        result = InputValidator.validate_choice("option2", choices)
        assert result == "option2"

    def test_validate_choice_invalid(self):
        """Test choice validation with invalid input."""
        choices = ["option1", "option2", "option3"]
        with pytest.raises(ValidationError, match="must be one of"):
            InputValidator.validate_choice("invalid", choices)

    def test_validate_search_type_valid(self):
        """Test search type validation with valid types."""
        assert InputValidator.validate_search_type("vector") == "vector"
        assert InputValidator.validate_search_type("keyword") == "keyword"
        assert InputValidator.validate_search_type("hybrid") == "hybrid"

    def test_validate_search_type_invalid(self):
        """Test search type validation with invalid type."""
        with pytest.raises(ValidationError, match="search type must be one of"):
            InputValidator.validate_search_type("invalid")

    def test_validate_index_type_valid(self):
        """Test index type validation with valid types."""
        assert InputValidator.validate_index_type("vector") == "vector"
        assert InputValidator.validate_index_type("keyword") == "keyword"
        assert InputValidator.validate_index_type("both") == "both"

    def test_validate_index_type_invalid(self):
        """Test index type validation with invalid type."""
        with pytest.raises(ValidationError, match="index type must be one of"):
            InputValidator.validate_index_type("invalid")

    def test_validate_config_key_valid(self):
        """Test config key validation with valid keys."""
        valid_keys = ["valid_key", "valid-key", "valid.key", "valid123", "a.b_c-d"]
        for key in valid_keys:
            assert InputValidator.validate_config_key(key) == key

    def test_validate_config_key_invalid(self):
        """Test config key validation with invalid keys."""
        invalid_keys = ["invalid key", "invalid@key", "invalid/key", ""]
        for key in invalid_keys:
            with pytest.raises(ValidationError, match="Invalid config key format"):
                InputValidator.validate_config_key(key)

    def test_validate_filter_expression_valid(self):
        """Test filter expression validation with valid JSON."""
        filter_str = '{"category": "electronics", "price": {"$gt": 100}}'
        result = InputValidator.validate_filter_expression(filter_str)
        assert result == {"category": "electronics", "price": {"$gt": 100}}

    def test_validate_filter_expression_invalid_json(self):
        """Test filter expression validation with invalid JSON."""
        with pytest.raises(ValidationError, match="Invalid filter JSON"):
            InputValidator.validate_filter_expression("invalid json")

    def test_validate_filter_expression_not_object(self):
        """Test filter expression validation with non-object JSON."""
        with pytest.raises(ValidationError, match="Filter must be a JSON object"):
            InputValidator.validate_filter_expression('"not an object"')

    def test_validate_file_patterns_valid(self):
        """Test file pattern validation with valid patterns."""
        patterns = ["*.pdf", "data/*.txt", "**/*.md"]
        result = InputValidator.validate_file_patterns(patterns)
        assert result == patterns

    def test_validate_file_patterns_path_traversal(self):
        """Test file pattern validation with path traversal."""
        with pytest.raises(ValidationError, match="Path traversal not allowed"):
            InputValidator.validate_file_patterns(["../secret.txt"])

    def test_validate_file_patterns_too_long(self):
        """Test file pattern validation with overly long pattern."""
        long_pattern = "a" * 101
        with pytest.raises(ValidationError, match="Pattern too long"):
            InputValidator.validate_file_patterns([long_pattern])

    @patch('builtins.input', return_value='y')
    def test_confirm_destructive_action_yes(self, mock_input):
        """Test destructive action confirmation with yes response."""
        result = InputValidator.confirm_destructive_action("Delete everything?")
        assert result is True

    @patch('builtins.input', return_value='n')
    def test_confirm_destructive_action_no(self, mock_input):
        """Test destructive action confirmation with no response."""
        result = InputValidator.confirm_destructive_action("Delete everything?")
        assert result is False

    def test_confirm_destructive_action_force(self):
        """Test destructive action confirmation with force flag."""
        result = InputValidator.confirm_destructive_action("Delete everything?", force=True)
        assert result is True

    @patch('builtins.input', side_effect=KeyboardInterrupt)
    def test_confirm_destructive_action_keyboard_interrupt(self, mock_input):
        """Test destructive action confirmation with keyboard interrupt."""
        result = InputValidator.confirm_destructive_action("Delete everything?")
        assert result is False

    def test_validate_workers_count_valid(self):
        """Test workers count validation with valid values."""
        assert InputValidator.validate_workers_count("5") == 5
        assert InputValidator.validate_workers_count(10) == 10
        assert InputValidator.validate_workers_count("32") == 32

    def test_validate_workers_count_too_high(self):
        """Test workers count validation with too high value."""
        with pytest.raises(ValidationError, match="Workers count too high"):
            InputValidator.validate_workers_count("50")

    def test_validate_workers_count_invalid(self):
        """Test workers count validation with invalid value."""
        with pytest.raises(ValidationError, match="workers count must be positive"):
            InputValidator.validate_workers_count("0")

    def test_validate_top_k_valid(self):
        """Test top-k validation with valid values."""
        assert InputValidator.validate_top_k("5") == 5
        assert InputValidator.validate_top_k(100) == 100
        assert InputValidator.validate_top_k("1000") == 1000

    def test_validate_top_k_too_high(self):
        """Test top-k validation with too high value."""
        with pytest.raises(ValidationError, match="Top-k too high"):
            InputValidator.validate_top_k("2000")

    def test_validate_top_k_invalid(self):
        """Test top-k validation with invalid value."""
        with pytest.raises(ValidationError, match="top-k must be positive"):
            InputValidator.validate_top_k("-5")
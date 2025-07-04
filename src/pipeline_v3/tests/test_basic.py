"""Basic tests to verify CI/CD pipeline functionality."""

import pytest


class TestBasic:
    """Basic tests for CI/CD verification."""

    def test_addition(self):
        """Test basic addition."""
        assert 2 + 2 == 4

    def test_string_concatenation(self):
        """Test string concatenation."""
        assert "hello" + " " + "world" == "hello world"

    def test_list_operations(self):
        """Test list operations."""
        test_list = [1, 2, 3]
        test_list.append(4)
        assert len(test_list) == 4
        assert test_list[-1] == 4

    @pytest.mark.parametrize(
        "input_val,expected",
        [
            (1, 2),
            (2, 4),
            (3, 6),
            (4, 8),
        ],
    )
    def test_multiplication(self, input_val, expected):
        """Test multiplication with parameters."""
        assert input_val * 2 == expected

    def test_dictionary_operations(self):
        """Test dictionary operations."""
        test_dict = {"key1": "value1"}
        test_dict["key2"] = "value2"
        assert len(test_dict) == 2
        assert "key2" in test_dict
        assert test_dict.get("key3", "default") == "default"


class TestExceptions:
    """Test exception handling."""

    def test_division_by_zero(self):
        """Test that division by zero raises exception."""
        with pytest.raises(ZeroDivisionError):
            _ = 1 / 0

    def test_key_error(self):
        """Test that accessing missing key raises exception."""
        test_dict = {"key": "value"}
        with pytest.raises(KeyError):
            _ = test_dict["missing_key"]

    def test_index_error(self):
        """Test that accessing invalid index raises exception."""
        test_list = [1, 2, 3]
        with pytest.raises(IndexError):
            _ = test_list[10]


@pytest.mark.unit
class TestMarkers:
    """Test with markers."""

    def test_with_unit_marker(self):
        """Test marked as unit test."""
        assert True

    @pytest.mark.slow
    def test_slow_operation(self):
        """Test marked as slow."""
        # Simulate slow operation
        result = sum(range(1000))
        assert result == 499500

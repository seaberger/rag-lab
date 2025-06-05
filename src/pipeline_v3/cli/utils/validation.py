"""
Input validation utilities for CLI.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


class ValidationError(Exception):
    """Raised when input validation fails."""
    pass


class InputValidator:
    """Handles validation of CLI inputs."""
    
    @staticmethod
    def validate_file_path(path: str, must_exist: bool = True) -> Path:
        """Validate file path input."""
        file_path = Path(path).expanduser().resolve()
        
        if must_exist and not file_path.exists():
            raise ValidationError(f"File does not exist: {path}")
        
        if must_exist and not file_path.is_file():
            raise ValidationError(f"Path is not a file: {path}")
        
        return file_path
    
    @staticmethod
    def validate_directory_path(path: str, must_exist: bool = True) -> Path:
        """Validate directory path input."""
        dir_path = Path(path).expanduser().resolve()
        
        if must_exist and not dir_path.exists():
            raise ValidationError(f"Directory does not exist: {path}")
        
        if must_exist and not dir_path.is_dir():
            raise ValidationError(f"Path is not a directory: {path}")
        
        return dir_path
    
    @staticmethod
    def validate_metadata(metadata_list: List[str]) -> Dict[str, Any]:
        """Validate and parse metadata key=value pairs."""
        metadata = {}
        
        for item in metadata_list:
            if '=' not in item:
                raise ValidationError(f"Invalid metadata format: '{item}' (expected key=value)")
            
            key, value = item.split('=', 1)
            key = key.strip()
            value = value.strip()
            
            if not key:
                raise ValidationError(f"Empty metadata key in: '{item}'")
            
            # Try to parse value as JSON for complex types
            try:
                parsed_value = json.loads(value)
                metadata[key] = parsed_value
            except json.JSONDecodeError:
                # Use as string if not valid JSON
                metadata[key] = value
        
        return metadata
    
    @staticmethod
    def validate_json(json_str: str) -> Dict[str, Any]:
        """Validate JSON string input."""
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON: {e}")
    
    @staticmethod
    def validate_positive_integer(value: Union[str, int], name: str = "value") -> int:
        """Validate positive integer input."""
        try:
            int_value = int(value)
            if int_value <= 0:
                raise ValidationError(f"{name} must be positive, got: {int_value}")
            return int_value
        except ValueError:
            raise ValidationError(f"{name} must be an integer, got: {value}")
    
    @staticmethod
    def validate_choice(value: str, choices: List[str], name: str = "value") -> str:
        """Validate choice from a list of options."""
        if value not in choices:
            choices_str = ", ".join(choices)
            raise ValidationError(f"{name} must be one of [{choices_str}], got: {value}")
        return value
    
    @staticmethod
    def validate_search_type(search_type: str) -> str:
        """Validate search type parameter."""
        valid_types = ['vector', 'keyword', 'hybrid']
        return InputValidator.validate_choice(search_type, valid_types, "search type")
    
    @staticmethod
    def validate_index_type(index_type: str) -> str:
        """Validate index type parameter."""
        valid_types = ['vector', 'keyword', 'both']
        return InputValidator.validate_choice(index_type, valid_types, "index type")
    
    @staticmethod
    def validate_config_key(key: str) -> str:
        """Validate configuration key format."""
        # Allow alphanumeric, dots, underscores, dashes
        if not re.match(r'^[a-zA-Z0-9._-]+$', key):
            raise ValidationError(f"Invalid config key format: {key}")
        return key
    
    @staticmethod
    def validate_filter_expression(filter_str: str) -> Dict[str, Any]:
        """Validate filter expression (JSON format)."""
        try:
            filter_dict = json.loads(filter_str)
            if not isinstance(filter_dict, dict):
                raise ValidationError("Filter must be a JSON object")
            return filter_dict
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid filter JSON: {e}")
    
    @staticmethod
    def validate_file_patterns(patterns: List[str]) -> List[str]:
        """Validate file glob patterns."""
        validated_patterns = []
        
        for pattern in patterns:
            # Basic validation - ensure no path traversal
            if '..' in pattern:
                raise ValidationError(f"Path traversal not allowed in pattern: {pattern}")
            
            # Ensure pattern is reasonable
            if len(pattern) > 100:
                raise ValidationError(f"Pattern too long (max 100 chars): {pattern}")
            
            validated_patterns.append(pattern)
        
        return validated_patterns
    
    @staticmethod
    def confirm_destructive_action(message: str, force: bool = False) -> bool:
        """Get user confirmation for destructive actions."""
        if force:
            return True
        
        try:
            response = input(f"{message} [y/N]: ").strip().lower()
            return response in ['y', 'yes']
        except (EOFError, KeyboardInterrupt):
            return False
    
    @staticmethod
    def validate_workers_count(workers: Union[str, int]) -> int:
        """Validate worker thread count."""
        count = InputValidator.validate_positive_integer(workers, "workers count")
        
        if count > 32:
            raise ValidationError(f"Workers count too high (max 32): {count}")
        
        return count
    
    @staticmethod
    def validate_top_k(top_k: Union[str, int]) -> int:
        """Validate top-k search parameter."""
        k = InputValidator.validate_positive_integer(top_k, "top-k")
        
        if k > 1000:
            raise ValidationError(f"Top-k too high (max 1000): {k}")
        
        return k
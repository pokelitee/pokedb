"""Utility functions and helpers for the PokéDB parser.

This package contains:
- exceptions: Custom exception classes
- constants: Constants used throughout the application
- file_ops: File and cache operations
- api_helpers: API interaction helpers
- text_utils: Text parsing and transformation utilities
"""

# Exceptions
# API helpers
from .api_helpers import get_generation_dex_map, get_latest_generation

# Constants
from .constants import (
    DEFAULT_API_LIMIT,
    MAX_ROMAN_NUMERAL,
    ROMAN_NUMERAL_MAP,
    SERVER_ERROR_CODES,
)
from .exceptions import (
    ConfigurationError,
    DataValidationError,
    GenerationNotFoundError,
    ParserExecutionError,
    PokeDBError,
    PokedexMappingError,
)

# File operations
from .file_ops import get_cache_path, write_json_atomic, write_json_file

# Text utilities
from .text_utils import (
    get_all_english_entries_by_version,
    get_all_english_entries_for_gen_by_game,
    get_english_entry,
    int_to_roman,
)

__all__ = [
    # Exceptions
    "PokeDBError",
    "GenerationNotFoundError",
    "PokedexMappingError",
    "ConfigurationError",
    "DataValidationError",
    "ParserExecutionError",
    # Constants
    "MAX_ROMAN_NUMERAL",
    "DEFAULT_API_LIMIT",
    "SERVER_ERROR_CODES",
    "ROMAN_NUMERAL_MAP",
    # File operations
    "get_cache_path",
    "write_json_file",
    "write_json_atomic",
    # API helpers
    "get_latest_generation",
    "get_generation_dex_map",
    # Text utilities
    "int_to_roman",
    "get_all_english_entries_for_gen_by_game",
    "get_all_english_entries_by_version",
    "get_english_entry",
]

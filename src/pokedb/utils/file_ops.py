"""File operations and caching utilities."""

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def write_json_atomic(file_path: Path, data: Any) -> None:
    """Writes JSON through a temporary file and atomically replaces the target."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=file_path.parent,
            prefix=f".{file_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(data, temporary_file, indent=4, ensure_ascii=False)
            temporary_file.flush()
        os.replace(temporary_path, file_path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def get_cache_path(url: str, cache_dir: str | Path) -> Path:
    """
    Generates a cache file path for a given URL using MD5 hashing.

    Args:
        url: The URL to generate a cache path for
        cache_dir: The directory where cache files are stored

    Returns:
        A Path object pointing to the cache file location

    Raises:
        ValueError: If cache_dir is not provided
    """
    if not cache_dir:
        raise ValueError("cache_dir must be provided to generate a cache path.")

    hashed_url = hashlib.md5(url.encode("utf-8")).hexdigest()
    return Path(cache_dir) / f"{hashed_url}.json"


def write_json_file(
    output_dir: str | Path, filename: str, data: dict[str, Any]
) -> Path:
    """Writes one parsed resource without rewriting dynamic identifier keys.

    Args:
        output_dir: The directory where the file should be written
        filename: The name of the file (without .json extension)
        data: The data dictionary to write

    Returns:
        Path to the written file
    """
    output_path = Path(output_dir)
    file_path = output_path / f"{filename}.json"
    write_json_atomic(file_path, data)

    return file_path

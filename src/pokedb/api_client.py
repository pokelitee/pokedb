import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter, Retry

from .config import Config
from .utils import SERVER_ERROR_CODES, get_cache_path, write_json_atomic

logger = logging.getLogger(__name__)


class ApiClient:
    """
    A memoized and file-cached API client for making requests to the PokéAPI.

    This client provides:
    - In-memory caching for repeated requests within the same session
    - File-based caching with configurable expiration
    - Automatic retry logic for server errors
    - Configurable timeout settings
    """

    def __init__(self, config: Config):
        """
        Initializes the ApiClient with configuration settings.

        Args:
            config: Configuration dictionary containing:
                - timeout: Request timeout in seconds (default: 15)
                - parser_cache_dir: Directory for cache files (optional)
                - cache_expires: Cache expiration time in seconds (optional)
                - max_retries: Maximum number of retry attempts (default: 3)
        """
        self._config = config
        self._thread_local = threading.local()
        self._cache_lock = threading.RLock()
        self._cache: dict[str, dict[str, Any]] = {}
        self.timeout = config.timeout
        self.cache_dir = config.parser_cache_dir
        self.cache_expires = config.cache_expires

        if self.cache_dir:
            Path(self.cache_dir).mkdir(parents=True, exist_ok=True)
            logger.debug(f"Cache directory initialized at {self.cache_dir}")

    def _setup_session(self, config: Config) -> requests.Session:
        """
        Creates a requests Session with automatic retry logic for server errors.

        Args:
            config: Configuration dictionary

        Returns:
            Configured requests.Session instance
        """
        session = requests.Session()
        retries = Retry(
            total=config.max_retries,
            backoff_factor=0.5,
            status_forcelist=SERVER_ERROR_CODES,
        )
        session.mount("https://", HTTPAdapter(max_retries=retries))
        session.mount("http://", HTTPAdapter(max_retries=retries))
        return session

    def _get_session(self) -> requests.Session:
        """Returns one reusable HTTP session per worker thread."""
        session = getattr(self._thread_local, "session", None)
        if session is None:
            session = self._setup_session(self._config)
            self._thread_local.session = session
        return session

    def get(self, url: str) -> dict[str, Any]:
        """
        Fetches JSON data from a URL, using both in-memory and file-based caches.

        The caching strategy is:
        1. Check in-memory cache first (fastest)
        2. Check file cache if enabled and not expired
        3. Make HTTP request if no valid cache exists
        4. Update both caches with the response

        Args:
            url: The API endpoint URL to fetch

        Returns:
            The JSON response as a dictionary

        Raises:
            requests.HTTPError: If the HTTP request fails
            requests.Timeout: If the request times out
            json.JSONDecodeError: If the response is not valid JSON
        """
        # Check in-memory cache first
        with self._cache_lock:
            if url in self._cache:
                logger.debug(f"Cache hit (memory): {url}")
                return self._cache[url]

        # Check file cache if enabled
        cache_file_path: Path | None = None
        if self.cache_dir:
            cache_file_path = get_cache_path(url, self.cache_dir)

            if cache_file_path.exists():
                file_mod_time = cache_file_path.stat().st_mtime
                cache_age = time.time() - file_mod_time

                if self.cache_expires is None or cache_age < self.cache_expires:
                    logger.debug(f"Cache hit (file): {url}")
                    try:
                        with cache_file_path.open("r", encoding="utf-8") as cache_file:
                            data = json.load(cache_file)
                    except (OSError, json.JSONDecodeError) as error:
                        logger.warning(
                            f"Ignoring unreadable cache entry {cache_file_path}: {error}"
                        )
                    else:
                        with self._cache_lock:
                            self._cache[url] = data
                        return data
                else:
                    logger.debug(f"Cache expired for: {url}")

        # Fetch from API
        logger.debug(f"Fetching from API: {url}")
        response = self._get_session().get(url, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()

        # Update in-memory cache
        with self._cache_lock:
            self._cache[url] = data

        # Update file cache if enabled
        if cache_file_path:
            write_json_atomic(cache_file_path, data)

        return data
